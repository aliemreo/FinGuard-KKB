from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from dotenv import load_dotenv
import os
import time
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
import io
import cv2
import numpy as np
import base64
from twocaptcha import TwoCaptcha
import argparse
import sys
import ollama

# Safe print function for Windows console
def safe_print(text):
    """Print text safely handling Unicode encoding errors on Windows"""
    try:
        print(text)
    except UnicodeEncodeError:
        # Replace problematic Unicode characters with ASCII equivalents
        text = text.replace('✓', '[OK]').replace('✗', '[X]')
        print(text)

class TicaretSicilLogin:
    def __init__(self, email, password, twocaptcha_api_key=None, pdf_output_dir='gazette_pdfs'):
        self.email = email
        self.password = password
        self.driver = None
        self.base_url = "https://www.ticaretsicil.gov.tr/index.php"
        self.twocaptcha_api_key = twocaptcha_api_key
        self.solver = TwoCaptcha(twocaptcha_api_key) if twocaptcha_api_key else None
        self.pdf_output_dir = os.path.abspath(pdf_output_dir)

    def setup_driver(self):
        """Initialize the Chrome WebDriver with automatic driver management"""
        options = webdriver.ChromeOptions()
        # Remove headless mode so you can see the CAPTCHA
        # options.add_argument('--headless')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        # Configure PDF auto-download
        # Create output directory if it doesn't exist
        os.makedirs(self.pdf_output_dir, exist_ok=True)

        prefs = {
            "download.default_directory": self.pdf_output_dir,
            "download.prompt_for_download": False,
            "plugins.always_open_pdf_externally": True,  # Download instead of opening in browser
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True
        }
        options.add_experimental_option("prefs", prefs)

        # Automatically download and use the correct ChromeDriver version
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.maximize_window()

    def preprocess_captcha_image(self, img, method='default'):
        """
        Apply various preprocessing techniques to improve OCR accuracy
        """
        # Convert PIL Image to numpy array for OpenCV processing
        img_array = np.array(img)

        if method == 'default':
            # Convert to grayscale
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            # Apply thresholding
            _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
            return Image.fromarray(thresh)

        elif method == 'adaptive':
            # Convert to grayscale
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            # Apply adaptive thresholding
            thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                          cv2.THRESH_BINARY, 11, 2)
            return Image.fromarray(thresh)

        elif method == 'denoise':
            # Convert to grayscale
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            # Denoise
            denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
            # Apply thresholding
            _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            return Image.fromarray(thresh)

        elif method == 'morphology':
            # Convert to grayscale
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            # Apply thresholding
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            # Morphological operations to remove noise
            kernel = np.ones((2, 2), np.uint8)
            opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
            return Image.fromarray(opening)

        elif method == 'enhance':
            # Use PIL for enhancement
            pil_img = Image.fromarray(img_array)
            # Convert to grayscale
            pil_img = pil_img.convert('L')
            # Enhance contrast
            enhancer = ImageEnhance.Contrast(pil_img)
            pil_img = enhancer.enhance(2.5)
            # Enhance sharpness
            enhancer = ImageEnhance.Sharpness(pil_img)
            pil_img = enhancer.enhance(2.0)
            # Apply threshold
            pil_img = pil_img.point(lambda x: 0 if x < 140 else 255, '1')
            return pil_img

        elif method == 'invert':
            # Convert to grayscale
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            # Invert colors
            inverted = cv2.bitwise_not(gray)
            # Apply thresholding
            _, thresh = cv2.threshold(inverted, 150, 255, cv2.THRESH_BINARY)
            return Image.fromarray(thresh)

        return img

    def solve_captcha_with_2captcha(self):
        """
        Solve CAPTCHA using 2Captcha service
        Returns the CAPTCHA text or None if failed
        """
        try:
            if not self.solver:
                print("2Captcha API key not provided")
                return None

            print("Solving CAPTCHA using 2Captcha service...")

            # Find the CAPTCHA image element
            captcha_img_element = self.driver.find_element(By.ID, "CaptchaImg")

            # Take a screenshot of the CAPTCHA
            captcha_png = captcha_img_element.screenshot_as_png

            # Convert to base64 for 2Captcha
            captcha_base64 = base64.b64encode(captcha_png).decode('utf-8')

            print("Sending CAPTCHA to 2Captcha... (this may take 10-30 seconds)")

            # Send to 2Captcha
            result = self.solver.normal(captcha_base64)

            if result and 'code' in result:
                captcha_text = result['code']
                safe_print(f"✓ 2Captcha solved: {captcha_text}")
                return captcha_text
            else:
                safe_print("✗ 2Captcha failed to solve")
                return None

        except Exception as e:
            print(f"Error with 2Captcha: {str(e)}")
            return None

    def solve_captcha_with_vlm(self, model='minicpm-v', confidence_threshold=0.6):
        """
        Solve CAPTCHA using Ollama Vision Language Model

        Args:
            model: Ollama vision model to use (default: minicpm-v)
            confidence_threshold: Minimum confidence to accept result (0.0-1.0)

        Returns:
            tuple: (captcha_text, confidence_score) or (None, 0.0) if failed
        """
        try:
            print(f"Solving CAPTCHA using VLM ({model})...")

            # Find the CAPTCHA image element
            captcha_img_element = self.driver.find_element(By.ID, "CaptchaImg")

            # Take a screenshot of the CAPTCHA
            captcha_png = captcha_img_element.screenshot_as_png

            # Convert to base64 for Ollama
            captcha_base64 = base64.b64encode(captcha_png).decode('utf-8')

            # Prompt engineering for CAPTCHA recognition
            system_prompt = """You are a CAPTCHA text recognition specialist.
Your task is to read the text from CAPTCHA images with high accuracy.
Return ONLY the alphanumeric text you see, nothing else.
The text is typically 4-6 characters containing letters and numbers."""

            user_prompt = """Read the text from this CAPTCHA image.
Return ONLY the alphanumeric characters you see.
Rules:
- No spaces, no special characters
- Capital letters if uppercase, lowercase if lowercase
- Numbers as digits
- If uncertain about a character, use your best guess

CAPTCHA Text:"""

            # Call Ollama VLM (first attempt)
            print("Sending CAPTCHA to VLM... (this may take 2-5 seconds)")
            response1 = ollama.chat(
                model=model,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt, 'images': [captcha_base64]}
                ],
                options={'temperature': 0.1}  # Low temperature for deterministic output
            )

            result1 = response1['message']['content'].strip()

            # Remove any spaces and special characters
            result1 = ''.join(c for c in result1 if c.isalnum())

            if not result1:
                print("VLM returned empty result")
                return (None, 0.0)

            # Calculate confidence score
            confidence = 0.0

            # Length validation (4-6 chars typical for CAPTCHA): +0.3
            if 4 <= len(result1) <= 6:
                confidence += 0.3
                print(f"  Length check passed: {len(result1)} chars")
            else:
                print(f"  Length check failed: {len(result1)} chars (expected 4-6)")

            # Alphanumeric check: +0.3
            if result1.isalnum():
                confidence += 0.3
                print(f"  Alphanumeric check passed")

            # Consistency check - ask again and compare: +0.4
            print("Verifying with second VLM call...")
            response2 = ollama.chat(
                model=model,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt, 'images': [captcha_base64]}
                ],
                options={'temperature': 0.1}
            )

            result2 = response2['message']['content'].strip()
            result2 = ''.join(c for c in result2 if c.isalnum())

            if result1 == result2:
                confidence += 0.4
                print(f"  Consistency check passed: both results match")
            else:
                print(f"  Consistency check failed: '{result1}' != '{result2}'")

            safe_print(f"✓ VLM Result: '{result1}' (confidence: {confidence:.2f})")

            if confidence >= confidence_threshold:
                return (result1, confidence)
            else:
                print(f"Confidence {confidence:.2f} below threshold {confidence_threshold}")
                return (None, confidence)

        except Exception as e:
            print(f"Error with VLM CAPTCHA solving: {str(e)}")
            import traceback
            traceback.print_exc()
            return (None, 0.0)

    def solve_captcha(self, save_debug=True):
        """
        Attempt to solve the CAPTCHA using OCR with multiple preprocessing methods
        Returns the CAPTCHA text or None if failed
        """
        try:
            print("Attempting to solve CAPTCHA using OCR...")

            # Find the CAPTCHA image element
            captcha_img_element = self.driver.find_element(By.ID, "CaptchaImg")

            # Take a screenshot of just the CAPTCHA element
            print("Taking screenshot of CAPTCHA...")
            captcha_png = captcha_img_element.screenshot_as_png
            img = Image.open(io.BytesIO(captcha_png))

            # Save original image for debugging
            if save_debug:
                img.save('captcha_original.png')
                print("Saved original CAPTCHA image as 'captcha_original.png'")

            # Resize image for better OCR (if too small)
            width, height = img.size
            if width < 100 or height < 30:
                scale_factor = 3
                img = img.resize((width * scale_factor, height * scale_factor), Image.LANCZOS)
                print(f"Resized image to {img.size}")

            # Try multiple preprocessing methods
            preprocessing_methods = ['enhance', 'default', 'denoise', 'adaptive', 'morphology', 'invert']

            # Different OCR configurations
            ocr_configs = [
                r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz',
                r'--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz',
                r'--oem 3 --psm 13 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz',
                r'--oem 1 --psm 7',
            ]

            results = {}

            for method in preprocessing_methods:
                processed_img = self.preprocess_captcha_image(img, method)

                if save_debug:
                    processed_img.save(f'captcha_{method}.png')

                for idx, config in enumerate(ocr_configs):
                    try:
                        text = pytesseract.image_to_string(processed_img, config=config).strip()
                        # Remove any spaces and special characters
                        text = ''.join(c for c in text if c.isalnum())

                        if text and len(text) >= 4:  # Assuming CAPTCHA is at least 4 characters
                            results[text] = results.get(text, 0) + 1
                            print(f"  Method '{method}' + Config {idx}: {text}")
                    except Exception as e:
                        continue

            # Find the most common result
            if results:
                best_result = max(results, key=results.get)
                confidence = results[best_result]
                safe_print(f"\n✓ Best OCR Result: '{best_result}' (appeared {confidence} times)")
                return best_result
            else:
                safe_print("✗ OCR failed to read CAPTCHA with all methods")
                return None

        except Exception as e:
            print(f"Error solving CAPTCHA: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def login(self, captcha_text=None, manual_captcha=True):
        """
        Login to the website

        Args:
            captcha_text: The CAPTCHA text if you want to provide it programmatically
            manual_captcha: If True, wait for user to manually enter CAPTCHA
        """
        try:
            # Navigate to the login page
            print(f"Navigating to {self.base_url}...")
            self.driver.get(self.base_url)

            # Wait for page to load
            print("Waiting for page to load...")
            time.sleep(3)

            # Click the login button to open the modal
            print("Opening login modal...")
            try:
                # Try multiple selectors to find the login button
                login_triggers = [
                    (By.LINK_TEXT, "GİRİŞ"),
                    (By.PARTIAL_LINK_TEXT, "GİRİŞ"),
                    (By.XPATH, "//a[contains(text(), 'GİRİŞ')]"),
                    (By.XPATH, "//a[contains(text(), 'Giriş')]"),
                    (By.CSS_SELECTOR, "a[href='#'][onclick*='giris']"),
                ]

                login_button = None
                for selector_type, selector_value in login_triggers:
                    try:
                        login_button = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((selector_type, selector_value))
                        )
                        print(f"Found login button using {selector_type}")
                        break
                    except:
                        continue

                if login_button:
                    login_button.click()
                    print("Login modal opened successfully")
                    time.sleep(2)
                else:
                    print("Warning: Could not find login button, form might already be visible")
            except Exception as e:
                print(f"Note: {str(e)}")
                print("Attempting to proceed anyway...")

            # Wait for the modal and form to appear
            print("Waiting for login form to appear...")
            time.sleep(2)

            # Find and fill email field
            print("Filling in email...")
            email_field = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.NAME, "LoginEmail"))
            )
            email_field.clear()
            email_field.send_keys(self.email)

            # Find and fill password field
            print("Filling in password...")
            password_field = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.NAME, "LoginSifre"))
            )
            password_field.clear()
            password_field.send_keys(self.password)

            # Handle CAPTCHA
            print("Locating CAPTCHA field...")
            captcha_field = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.NAME, "Captcha"))
            )

            # Try to solve CAPTCHA automatically first
            if not captcha_text:
                # Try VLM first (free, ~60-70% accuracy)
                try:
                    captcha_text, vlm_confidence = self.solve_captcha_with_vlm()
                    if captcha_text:
                        safe_print(f"✓ VLM solved CAPTCHA with confidence: {vlm_confidence:.2f}")
                    else:
                        print("VLM confidence too low, trying 2Captcha...")
                except Exception as e:
                    print(f"VLM failed: {e}, trying 2Captcha...")
                    captcha_text = None

                # Fall back to 2Captcha if VLM fails
                if not captcha_text and self.twocaptcha_api_key:
                    captcha_text = self.solve_captcha_with_2captcha()

                # Fall back to OCR if both VLM and 2Captcha fail
                if not captcha_text:
                    captcha_text = self.solve_captcha()

            if captcha_text:
                print(f"Filling in CAPTCHA with: {captcha_text}")

                # Ensure the field is focused and ready
                captcha_field.click()
                time.sleep(0.5)

                # Clear the field
                captcha_field.clear()
                time.sleep(0.3)

                # Fill in the CAPTCHA text
                captcha_field.send_keys(captcha_text)
                time.sleep(0.5)

                # Verify the value was entered
                entered_value = captcha_field.get_attribute('value')
                print(f"Verified CAPTCHA entered: {entered_value}")

                if entered_value != captcha_text:
                    print(f"Warning: Entered value '{entered_value}' doesn't match '{captcha_text}'")
                    # Try using JavaScript as backup
                    print("Attempting to fill using JavaScript...")
                    self.driver.execute_script(
                        "arguments[0].value = arguments[1];",
                        captcha_field,
                        captcha_text
                    )
                    time.sleep(0.3)
                    entered_value = captcha_field.get_attribute('value')
                    print(f"Value after JavaScript fill: {entered_value}")
            elif manual_captcha:
                print("\n" + "="*50)
                print("MANUAL CAPTCHA ENTRY REQUIRED")
                print("="*50)
                print("OCR failed. Please look at the browser window and enter the CAPTCHA.")
                print("After entering the CAPTCHA, the script will automatically proceed.")
                print("="*50 + "\n")

                # Wait for user to enter CAPTCHA (check if field has value)
                wait_time = 60  # Wait up to 60 seconds
                for _ in range(wait_time):
                    if captcha_field.get_attribute('value'):
                        print("CAPTCHA entered! Proceeding with login...")
                        break
                    time.sleep(1)
                else:
                    print("Timeout waiting for CAPTCHA entry.")
                    return False
            else:
                print("No CAPTCHA solution available")
                return False

            # Find and click the login button
            print("Submitting login form...")
            login_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
            login_button.click()

            # Wait for login to process
            time.sleep(3)

            # Check if login was successful
            # You can add specific success indicators here based on the website's response
            current_url = self.driver.current_url
            print(f"Current URL after login: {current_url}")

            # Check for error messages
            try:
                error_elements = self.driver.find_elements(By.CLASS_NAME, "error")
                if error_elements and any(elem.is_displayed() for elem in error_elements):
                    print("Login failed - error message detected")
                    return False
            except:
                pass

            print("Login successful!")
            return True

        except TimeoutException:
            print("Timeout: Could not find login form elements")
            return False
        except Exception as e:
            print(f"Error during login: {str(e)}")
            return False

    def convert_date_format(self, iso_date):
        """
        Convert ISO date (YYYY-MM-DD) to Turkish format (DD.MM.YYYY)

        Args:
            iso_date: Date string in YYYY-MM-DD format

        Returns:
            Date string in DD.MM.YYYY format

        Raises:
            ValueError: If date format is invalid
        """
        from datetime import datetime
        try:
            date_obj = datetime.strptime(iso_date, '%Y-%m-%d')
            return date_obj.strftime('%d.%m.%Y')
        except ValueError:
            raise ValueError(f"Invalid date format. Expected YYYY-MM-DD, got: {iso_date}")

    def fetch_trade_registry_announcement(self, sicil_mudurugu, ticaret_sicil_no,
                                         start_date=None, end_date=None):
        """
        Navigate to the announcement page and fetch results

        Args:
            sicil_mudurugu: Name or ID of the registry office (e.g., "İSTANBUL" or "232")
            ticaret_sicil_no: Trade registry number
            start_date: Start date in YYYY-MM-DD format (optional)
            end_date: End date in YYYY-MM-DD format (optional)
        """
        try:
            print(f"\n{'='*50}")
            print("FETCHING TRADE REGISTRY ANNOUNCEMENT")
            print(f"{'='*50}")

            # Navigate to the announcement page
            announcement_url = "https://www.ticaretsicil.gov.tr/view/hizlierisim/ilangoruntuleme.php"
            print(f"Navigating to {announcement_url}...")
            self.driver.get(announcement_url)
            time.sleep(3)

            # Select the registry office (Sicil Müdürlüğü)
            print(f"Selecting registry office: {sicil_mudurugu}")
            select_element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "SicilMudurluguId"))
            )

            from selenium.webdriver.support.ui import Select
            select = Select(select_element)

            # Try to select by visible text first, then by value
            try:
                select.select_by_visible_text(sicil_mudurugu)
            except:
                try:
                    select.select_by_value(str(sicil_mudurugu))
                except:
                    print(f"Could not find option: {sicil_mudurugu}")
                    return None

            time.sleep(2)

            # Find and fill the Trade Registry Number field
            print(f"Entering trade registry number: {ticaret_sicil_no}")

            # Try multiple selectors to find the trade registry number field
            sicil_no_field = None
            possible_selectors = [
                (By.NAME, "TicSicNo"),  # The actual field name!
                (By.ID, "TicSicNo"),
                (By.NAME, "TicaretSicilNo"),
                (By.NAME, "SicilNo"),
                (By.ID, "TicaretSicilNo"),
                (By.ID, "SicilNo"),
                (By.CSS_SELECTOR, "input[placeholder*='Ticaret Sicili No']"),
                (By.CSS_SELECTOR, "input[type='text'][name*='Sicil']"),
            ]

            for selector_type, selector_value in possible_selectors:
                try:
                    sicil_no_field = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((selector_type, selector_value))
                    )
                    print(f"Found registry number field using {selector_type}: {selector_value}")
                    break
                except:
                    continue

            if not sicil_no_field:
                # Try to find all input fields and print them for debugging
                print("Could not find trade registry number field. Available input fields:")
                all_inputs = self.driver.find_elements(By.TAG_NAME, "input")
                for inp in all_inputs:
                    inp_type = inp.get_attribute('type')
                    inp_name = inp.get_attribute('name')
                    inp_id = inp.get_attribute('id')
                    inp_placeholder = inp.get_attribute('placeholder')
                    print(f"  - Type: {inp_type}, Name: {inp_name}, ID: {inp_id}, Placeholder: {inp_placeholder}")
                return None

            # Scroll to the element to ensure it's visible
            self.driver.execute_script("arguments[0].scrollIntoView(true);", sicil_no_field)
            time.sleep(0.5)

            # Try to interact with the field
            try:
                sicil_no_field.clear()
                sicil_no_field.send_keys(ticaret_sicil_no)
            except:
                # If regular interaction fails, use JavaScript
                print("Using JavaScript to fill the field...")
                self.driver.execute_script(
                    "arguments[0].value = arguments[1];",
                    sicil_no_field,
                    ticaret_sicil_no
                )
                # Trigger change event
                self.driver.execute_script(
                    "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));",
                    sicil_no_field
                )

            time.sleep(1)
            safe_print(f"✓ Successfully entered: {ticaret_sicil_no}")

            # Handle date range if provided
            if start_date and end_date:
                try:
                    print(f"Setting date range: {start_date} to {end_date}")

                    # 1. Find and click the date checkbox
                    date_checkbox = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.ID, "Tarih"))
                    )

                    if not date_checkbox.is_selected():
                        # Scroll to checkbox
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", date_checkbox)
                        time.sleep(0.3)
                        date_checkbox.click()
                        print("✓ Date range checkbox activated")
                        time.sleep(1)  # Wait for date fields to appear

                    # 2. Convert dates to Turkish format (DD.MM.YYYY)
                    start_turkish = self.convert_date_format(start_date)
                    end_turkish = self.convert_date_format(end_date)
                    print(f"Converted dates: {start_turkish} - {end_turkish}")

                    # 3. Find and fill date fields
                    # Try multiple possible field names
                    start_date_selectors = [
                        (By.NAME, "BaslangicTarihi"),
                        (By.NAME, "IlkTarih"),
                        (By.NAME, "TarihBas"),
                        (By.ID, "BaslangicTarihi"),
                        (By.ID, "IlkTarih"),
                        (By.CSS_SELECTOR, "input[name*='Baslangic']"),
                        (By.CSS_SELECTOR, "input[id*='Baslangic']"),
                    ]

                    end_date_selectors = [
                        (By.NAME, "BitisTarihi"),
                        (By.NAME, "SonTarih"),
                        (By.NAME, "TarihBit"),
                        (By.ID, "BitisTarihi"),
                        (By.ID, "SonTarih"),
                        (By.CSS_SELECTOR, "input[name*='Bitis']"),
                        (By.CSS_SELECTOR, "input[id*='Bitis']"),
                    ]

                    # Find start date field
                    start_date_field = None
                    for selector_type, selector_value in start_date_selectors:
                        try:
                            start_date_field = WebDriverWait(self.driver, 3).until(
                                EC.presence_of_element_located((selector_type, selector_value))
                            )
                            print(f"Found start date field using {selector_type}: {selector_value}")
                            break
                        except:
                            continue

                    # Find end date field
                    end_date_field = None
                    for selector_type, selector_value in end_date_selectors:
                        try:
                            end_date_field = WebDriverWait(self.driver, 3).until(
                                EC.presence_of_element_located((selector_type, selector_value))
                            )
                            print(f"Found end date field using {selector_type}: {selector_value}")
                            break
                        except:
                            continue

                    if start_date_field and end_date_field:
                        # Fill start date
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", start_date_field)
                        time.sleep(0.3)
                        start_date_field.clear()
                        start_date_field.send_keys(start_turkish)

                        # Fill end date
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", end_date_field)
                        time.sleep(0.3)
                        end_date_field.clear()
                        end_date_field.send_keys(end_turkish)

                        safe_print(f"✓ Date range set: {start_turkish} - {end_turkish}")
                        time.sleep(0.5)
                    else:
                        print("Warning: Could not find date fields")
                        if not start_date_field:
                            print("  - Start date field not found")
                        if not end_date_field:
                            print("  - End date field not found")
                        print("Proceeding without date filter...")

                except Exception as e:
                    print(f"Warning: Could not set date range: {e}")
                    print("Proceeding without date filter...")

            # Submit the form
            print("Submitting form...")

            # Try multiple selectors for the submit button
            submit_button = None
            button_selectors = [
                (By.CSS_SELECTOR, "button[type='submit'][data-message='İlan Ara']"),
                (By.CSS_SELECTOR, "button[type='submit'].c-theme-btn"),
                (By.CSS_SELECTOR, "button.btn.c-theme-btn.c-btn-uppercase"),
                (By.XPATH, "//button[@type='submit' and contains(@class, 'c-theme-btn')]"),
                (By.CSS_SELECTOR, "button[type='submit'] i.fa-search"),  # Button containing search icon
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.CSS_SELECTOR, "input[type='submit']"),
                (By.XPATH, "//button[contains(text(), 'Ara') or contains(text(), 'ara')]"),
                (By.XPATH, "//input[@value='Ara' or @value='ARA']"),
                (By.CSS_SELECTOR, "button.btn"),
                (By.TAG_NAME, "button"),
            ]

            for selector_type, selector_value in button_selectors:
                try:
                    submit_button = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((selector_type, selector_value))
                    )
                    print(f"Found submit button using {selector_type}")
                    break
                except:
                    continue

            if not submit_button:
                print("Could not find submit button, trying JavaScript submit...")
                # Try to submit the form via JavaScript
                self.driver.execute_script("""
                    var forms = document.getElementsByTagName('form');
                    if (forms.length > 0) {
                        forms[forms.length - 1].submit();
                    }
                """)
            else:
                # Try to click, with JavaScript fallback
                try:
                    # Scroll to button
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", submit_button)
                    time.sleep(0.5)
                    submit_button.click()
                except:
                    print("Regular click failed, using JavaScript...")
                    self.driver.execute_script("arguments[0].click();", submit_button)

            # Wait for results to load
            print("Waiting for results to load...")
            time.sleep(3)

            # Wait for either results to appear or error message
            # Results typically appear in a table or specific container
            try:
                # Wait up to 30 seconds for results to load
                WebDriverWait(self.driver, 30).until(
                    lambda driver: (
                        # Check if results table/container appeared
                        len(driver.find_elements(By.TAG_NAME, "table")) > 0 or
                        # Or check if "sonuç" (result) appears in page
                        "sonuç" in driver.page_source.lower() or
                        "kayıt" in driver.page_source.lower() or
                        # Or check if no results message appears
                        "bulunamadı" in driver.page_source.lower() or
                        "bulunamamıştır" in driver.page_source.lower()
                    )
                )
                print("Results loaded or no results message appeared")
            except TimeoutException:
                print("Timeout waiting for results, but continuing anyway...")

            # Additional wait to ensure JavaScript finishes rendering
            time.sleep(2)

            # Get the page source after results load
            page_source = self.driver.page_source

            safe_print("✓ Form submitted successfully!")
            print(f"Current URL: {self.driver.current_url}")

            # Check if results actually appeared
            if "sonuç" in page_source.lower() or "kayıt" in page_source.lower():
                print("✓ Results detected in page")
            elif "bulunamadı" in page_source.lower() or "bulunamamıştır" in page_source.lower():
                print("! No results found for this query")
            else:
                print("? Could not determine if results loaded - page source saved anyway")

            return page_source

        except Exception as e:
            print(f"Error fetching trade registry announcement: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def download_pdf_from_results(self, max_pdfs=None):
        """
        Download PDFs from search results by navigating to them in browser
        This preserves full session state and triggers Chrome's auto-download

        Args:
            max_pdfs: Maximum number of PDFs to download (None = all, or specify N for most recent N)

        Returns:
            List of paths to downloaded PDFs or empty list if failed
        """
        try:
            print("\n" + "="*50)
            print("DOWNLOADING PDFs FROM RESULTS")
            print("="*50)

            # Wait a moment for the page to be fully loaded
            time.sleep(2)

            # Save current window handle
            original_window = self.driver.current_window_handle

            # Find ALL PDF links in results table
            print("Looking for PDF links in results...")
            try:
                # Try multiple selectors to find PDF links
                pdf_links = []
                pdf_selectors = [
                    (By.CSS_SELECTOR, "a[href*='pdf_goster.php']"),
                    (By.XPATH, "//a[contains(@href, 'pdf_goster.php')]"),
                ]

                for selector_type, selector_value in pdf_selectors:
                    try:
                        links = self.driver.find_elements(selector_type, selector_value)
                        if links:
                            pdf_links = links
                            print(f"Found {len(pdf_links)} PDF link(s) using {selector_type}")
                            break
                    except:
                        continue

                if not pdf_links:
                    print("No PDF links found in search results")
                    return []

            except Exception as e:
                print(f"Could not find PDF links: {e}")
                return []

            # Extract all PDF URLs first
            pdf_urls = []
            for link in pdf_links:
                try:
                    url = link.get_attribute('href')
                    if url and 'pdf_goster.php' in url:
                        pdf_urls.append(url)
                except:
                    continue

            print(f"Found {len(pdf_urls)} total PDF link(s) on page")

            # Deduplicate URLs (same PDF link might appear multiple times)
            unique_urls = list(dict.fromkeys(pdf_urls))  # Preserves order
            if len(unique_urls) < len(pdf_urls):
                print(f"After deduplication: {len(unique_urls)} unique PDF(s)")
            pdf_urls = unique_urls

            # Limit to max_pdfs if specified
            if max_pdfs and max_pdfs < len(pdf_urls):
                print(f"Limiting to {max_pdfs} most recent PDF(s)")
                pdf_urls = pdf_urls[:max_pdfs]

            # Show all URLs for debugging
            for idx, url in enumerate(pdf_urls, 1):
                print(f"  PDF {idx}: ...{url[-60:]}")  # Show last 60 chars to see GUID

            # Get list of existing files before downloading
            existing_files = set()
            if os.path.exists(self.pdf_output_dir):
                existing_files = set(os.listdir(self.pdf_output_dir))

            # Download each PDF by navigating to it in a new tab
            downloaded_files = []

            for idx, pdf_url in enumerate(pdf_urls, 1):
                try:
                    print(f"\nDownloading PDF {idx}/{len(pdf_urls)}...")
                    print(f"URL: {pdf_url}")

                    # Open PDF in new tab
                    self.driver.execute_script(f"window.open('{pdf_url}', '_blank');")

                    # Switch to new tab
                    self.driver.switch_to.window(self.driver.window_handles[-1])

                    # Wait for download to start (Chrome should auto-download with our settings)
                    print("Waiting for download to complete...")
                    time.sleep(5)  # Give Chrome time to download

                    # Close the tab
                    self.driver.close()

                    # Switch back to original window
                    self.driver.switch_to.window(original_window)

                    # Check if new file appeared in download directory
                    if os.path.exists(self.pdf_output_dir):
                        current_files = set(os.listdir(self.pdf_output_dir))
                        new_files = current_files - existing_files
                        if new_files:
                            # Find the most recently modified file
                            newest_file = max(
                                [os.path.join(self.pdf_output_dir, f) for f in new_files],
                                key=os.path.getmtime
                            )
                            # Rename to gazette_N.pdf
                            new_filename = f"gazette_{idx}.pdf"
                            new_filepath = os.path.join(self.pdf_output_dir, new_filename)

                            # If file already exists with this name, remove it
                            if os.path.exists(new_filepath):
                                os.remove(new_filepath)

                            os.rename(newest_file, new_filepath)
                            file_size = os.path.getsize(new_filepath) / 1024  # KB
                            safe_print(f"✓ PDF {idx} downloaded: {new_filename} ({file_size:.1f} KB)")
                            downloaded_files.append(new_filepath)
                            existing_files = current_files  # Update for next iteration
                        else:
                            print(f"✗ PDF {idx}: No new file detected in download directory")
                    else:
                        print(f"✗ PDF {idx}: Download directory not found")

                except Exception as e:
                    print(f"✗ PDF {idx}: Error - {e}")
                    # Make sure we're back on the original window
                    try:
                        self.driver.switch_to.window(original_window)
                    except:
                        pass

            if downloaded_files:
                safe_print(f"\n✓ Successfully downloaded {len(downloaded_files)}/{len(pdf_urls)} PDF(s)")
                return downloaded_files
            else:
                print(f"\n✗ No PDFs were downloaded out of {len(pdf_urls)} found")
                return []

        except Exception as e:
            print(f"Error downloading PDFs: {str(e)}")
            import traceback
            traceback.print_exc()
            return []

    def keep_session_alive(self, duration=300):
        """
        Keep the browser session alive for a specified duration

        Args:
            duration: Time in seconds to keep session alive (default: 5 minutes)
        """
        print(f"Keeping session alive for {duration} seconds...")
        time.sleep(duration)

    def close(self):
        """Close the browser"""
        if self.driver:
            print("Closing browser...")
            self.driver.quit()


def validate_date_range(start_date, end_date):
    """
    Validate date format and range

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Raises:
        ValueError: If dates are invalid or start > end
    """
    from datetime import datetime

    try:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')

        if start > end:
            raise ValueError("start_date must be before or equal to end_date")

    except ValueError as e:
        if "does not match format" in str(e) or "unconverted data" in str(e):
            raise ValueError(f"Invalid date format. Expected YYYY-MM-DD format. Error: {e}")
        raise


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Trade Registry Announcement Fetcher',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python ticaret_sicil_scraper.py --office ANKARA --number 31177

  # With date range
  python ticaret_sicil_scraper.py --office ANKARA --number 31177 \\
      --start-date 2024-01-01 --end-date 2024-12-31

  # Download PDF from results
  python ticaret_sicil_scraper.py --office ANKARA --number 31177 --download-pdf

  # Download only the 2 most recent PDFs
  python ticaret_sicil_scraper.py --office ANKARA --number 31177 --download-pdf --max-pdfs 2

  # Full featured: date range + PDF download
  python ticaret_sicil_scraper.py --office ANKARA --number 31177 \\
      --start-date 2024-01-01 --end-date 2024-12-31 \\
      --download-pdf --pdf-output-dir my_gazettes

  # Interactive mode (legacy)
  python ticaret_sicil_scraper.py --interactive
"""
    )

    # Mode selection
    parser.add_argument('--interactive', action='store_true',
                        help='Use interactive input mode (legacy)')

    # Required arguments (unless in interactive mode)
    parser.add_argument('--office', type=str,
                        help='Registry office name or ID (e.g., ANKARA or 18)')
    parser.add_argument('--number', type=str,
                        help='Trade registry number (e.g., 31177)')

    # Optional date filtering
    parser.add_argument('--start-date', type=str,
                        help='Start date for filtering (YYYY-MM-DD format)')
    parser.add_argument('--end-date', type=str,
                        help='End date for filtering (YYYY-MM-DD format)')

    # CAPTCHA options
    parser.add_argument('--no-vlm', action='store_true',
                        help='Skip VLM CAPTCHA solving, use 2Captcha/OCR only')

    # PDF download options
    parser.add_argument('--download-pdf', action='store_true',
                        help='Download PDF from search results')
    parser.add_argument('--pdf-output-dir', type=str, default='gazette_pdfs',
                        help='Directory to save downloaded PDFs (default: gazette_pdfs)')
    parser.add_argument('--max-pdfs', type=int,
                        help='Maximum number of PDFs to download (default: all). Use to limit to N most recent PDFs')

    args = parser.parse_args()

    # Validate arguments
    if not args.interactive:
        # In non-interactive mode, --office and --number are required
        if not args.office or not args.number:
            parser.error("--office and --number are required (or use --interactive for legacy mode)")

    # Validate date range if provided
    if args.start_date or args.end_date:
        if not (args.start_date and args.end_date):
            parser.error("--start-date and --end-date must be provided together")

        try:
            validate_date_range(args.start_date, args.end_date)
        except ValueError as e:
            parser.error(str(e))

    # Load environment variables from .env file
    load_dotenv()

    EMAIL = os.getenv('EMAIL')
    PASSWORD = os.getenv('PASSWORD')
    TWOCAPTCHA_API_KEY = os.getenv('TWOCAPTCHA_API_KEY')

    if not EMAIL or not PASSWORD:
        print("Error: EMAIL and PASSWORD must be set in .env file")
        print("Please create a .env file with:")
        print("EMAIL=your_email@example.com")
        print("PASSWORD=your_password")
        return

    if not TWOCAPTCHA_API_KEY:
        print("\nWarning: TWOCAPTCHA_API_KEY not found in .env file")
        print("CAPTCHA solving will fall back to OCR (less reliable)")
        print("To use 2Captcha service:")
        print("1. Sign up at https://2captcha.com")
        print("2. Add TWOCAPTCHA_API_KEY=your_api_key to .env file\n")

    # Create login instance
    login = TicaretSicilLogin(EMAIL, PASSWORD, TWOCAPTCHA_API_KEY, args.pdf_output_dir)

    try:
        # Setup the browser
        login.setup_driver()

        # Perform login (with manual CAPTCHA entry)
        success = login.login(manual_captcha=True)

        if success:
            print("\n" + "="*50)
            print("Successfully logged in!")
            print("="*50 + "\n")

            # Determine if we should fetch registry data
            if args.interactive:
                # Interactive mode (legacy)
                print("Running in INTERACTIVE mode...")
                print("Do you want to fetch trade registry announcements?")
                print("Enter 'y' to fetch, or 'n' to just keep session alive: ", end='')
                fetch_choice = input().strip().lower()

                if fetch_choice == 'y':
                    # Get registry office
                    print("\nEnter Sicil Müdürlüğü (e.g., İSTANBUL or 232): ", end='')
                    sicil_mudurugu = input().strip()

                    # Get trade registry number
                    print("Enter Ticaret Sicil No: ", end='')
                    ticaret_sicil_no = input().strip()

                    # Optional date range in interactive mode
                    use_dates = input("Filter by date range? (y/n): ").strip().lower()
                    if use_dates == 'y':
                        start_date = input("Start date (YYYY-MM-DD): ").strip()
                        end_date = input("End date (YYYY-MM-DD): ").strip()
                    else:
                        start_date = None
                        end_date = None
                else:
                    start_date = None
                    end_date = None
            else:
                # Automatic mode with command-line arguments
                fetch_choice = 'y'
                sicil_mudurugu = args.office
                ticaret_sicil_no = args.number
                start_date = args.start_date
                end_date = args.end_date

                print(f"Registry Office: {sicil_mudurugu}")
                print(f"Registry Number: {ticaret_sicil_no}")
                if start_date and end_date:
                    print(f"Date Range: {start_date} to {end_date}")

            if fetch_choice == 'y':
                # Fetch the announcement
                page_source = login.fetch_trade_registry_announcement(
                    sicil_mudurugu,
                    ticaret_sicil_no,
                    start_date,
                    end_date
                )

                if page_source:
                    # Download PDFs if requested
                    if args.download_pdf:
                        print("\nDownloading PDFs from results...")
                        pdf_paths = login.download_pdf_from_results(max_pdfs=args.max_pdfs)
                        if pdf_paths:
                            safe_print(f"✓ Downloaded {len(pdf_paths)} PDF(s)")
                            for path in pdf_paths:
                                print(f"  - {os.path.basename(path)}")
                        else:
                            print("✗ No PDFs were downloaded")

                    # Keep browser open to see results
                    print("\nBrowser will stay open for 60 seconds so you can review the results...")
                    login.keep_session_alive(duration=60)
                else:
                    safe_print("\n[X] Failed to fetch results")
            else:
                # Keep the session alive for 5 minutes
                print("Keeping session alive for 5 minutes...")
                login.keep_session_alive(duration=300)

        else:
            print("Login failed!")

    except KeyboardInterrupt:
        print("\nProcess interrupted by user")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
    finally:
        # Close the browser
        login.close()


if __name__ == "__main__":
    main()
