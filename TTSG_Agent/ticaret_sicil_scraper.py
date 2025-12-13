from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
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
import argparse
import sys
import ollama
import requests


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
    def __init__(self, email, password, pdf_output_dir='gazette_pdfs'):
        self.email = email
        self.password = password
        self.driver = None
        self.base_url = "https://www.ticaretsicil.gov.tr/index.php"
        self.pdf_output_dir = os.path.abspath(pdf_output_dir)
        self.current_office = None  # Store current registry office for filename
        self.current_company = None  # Store current company name for filename

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
        print(f"PDF download directory: {self.pdf_output_dir}")

        prefs = {
            "download.default_directory": self.pdf_output_dir,
            "download.prompt_for_download": False,
            "plugins.always_open_pdf_externally": True,  # Download instead of opening in browser
            "download.directory"
            "_upgrade": True,
            "safebrowsing.enabled": True,
            "profile.default_content_settings.popups": 0,
            "download.extensions_to_open": "",
            "plugins.plugins_disabled": ["Chrome PDF Viewer"]
        }
        options.add_experimental_option("prefs", prefs)

        # Additional arguments to help with downloads
        options.add_argument('--disable-popup-blocking')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')

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

    def _process_captcha_with_vlm(self, captcha_base64, model='minicpm-v', confidence_threshold=0.6):
        """
        Process a base64-encoded CAPTCHA image with VLM

        Args:
            captcha_base64: Base64-encoded image data
            model: Ollama vision model to use
            confidence_threshold: Minimum confidence to accept result

        Returns:
            tuple: (captcha_text, confidence_score) or (None, 0.0) if failed
        """
        try:
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

            print("Sending CAPTCHA to VLM... (this may take 2-5 seconds)")
            response1 = ollama.chat(
                model=model,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt, 'images': [captcha_base64]}
                ],
                options={'temperature': 0.1}
            )

            result1 = response1['message']['content'].strip()
            result1 = ''.join(c for c in result1 if c.isalnum())

            if not result1:
                print("VLM returned empty result")
                return (None, 0.0)

            confidence = 0.0
            if 4 <= len(result1) <= 6:
                confidence += 0.3
                print(f"  Length check passed: {len(result1)} chars")
            else:
                print(f"  Length check failed: {len(result1)} chars (expected 4-6)")

            if result1.isalnum():
                confidence += 0.3
                print(f"  Alphanumeric check passed")

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
            print(f"Error processing CAPTCHA with VLM: {str(e)}")
            return (None, 0.0)

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

            # Wait for CAPTCHA image to be visible (not just present)
            # This handles modals/overlays that take time to render
            captcha_img_element = None
            max_visibility_wait = 10
            switched_to_iframe = False

            for wait_attempt in range(max_visibility_wait):
                try:
                    # First check if element exists in main document
                    captcha_img_element = self.driver.find_element(By.ID, "CaptchaImg")

                    # Check visibility and dimensions
                    if captcha_img_element.is_displayed():
                        size = captcha_img_element.size
                        if size['width'] > 0 and size['height'] > 0:
                            print(f"CAPTCHA image visible after {wait_attempt + 1}s (size: {size['width']}x{size['height']})")
                            break

                    print(f"Waiting for CAPTCHA image to be visible... ({wait_attempt + 1}/{max_visibility_wait})")
                    time.sleep(1)
                except:
                    # Element not found - try checking iframes
                    if not switched_to_iframe:
                        try:
                            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                            for iframe in iframes:
                                try:
                                    self.driver.switch_to.frame(iframe)
                                    captcha_img_element = self.driver.find_element(By.ID, "CaptchaImg")
                                    if captcha_img_element:
                                        switched_to_iframe = True
                                        print("Found CAPTCHA in iframe")
                                        break
                                except:
                                    self.driver.switch_to.default_content()
                        except:
                            pass

                    print(f"Waiting for CAPTCHA image element... ({wait_attempt + 1}/{max_visibility_wait})")
                    time.sleep(1)

            if not captcha_img_element:
                # Debug: print what elements exist
                print("CAPTCHA image element not found. Debugging info:")
                try:
                    form = self.driver.find_element(By.ID, "FormGuvenlikKodu")
                    print(f"  Form found: {form.tag_name}, visible: {form.is_displayed()}")
                    # List all img elements in the form
                    imgs = form.find_elements(By.TAG_NAME, "img")
                    print(f"  Found {len(imgs)} img elements in form:")
                    for i, img in enumerate(imgs):
                        print(f"    img[{i}]: id='{img.get_attribute('id')}', class='{img.get_attribute('class')}', visible={img.is_displayed()}")
                except Exception as debug_err:
                    print(f"  Debug error: {debug_err}")
                return (None, 0.0)

            # Check image src and dimensions
            img_src = captcha_img_element.get_attribute('src')
            size = captcha_img_element.size
            print(f"  CAPTCHA image src: {img_src[:80] if img_src else 'None'}...")
            print(f"  Size: {size}, Displayed: {captcha_img_element.is_displayed()}")

            # If image has 0 dimensions, try to reload/refresh the CAPTCHA
            if size['width'] == 0 or size['height'] == 0:
                print("CAPTCHA image has 0 dimensions, trying to reload...")

                # Try clicking a refresh button if it exists
                try:
                    refresh_btn = self.driver.find_element(By.CSS_SELECTOR, "a[onclick*='yenile'], button[onclick*='yenile'], #refreshCaptcha, .refresh-captcha")
                    refresh_btn.click()
                    print("  Clicked refresh button")
                    time.sleep(2)
                    # Re-find the element
                    captcha_img_element = self.driver.find_element(By.ID, "CaptchaImg")
                    size = captcha_img_element.size
                except:
                    pass

                # Try to force load the image with JavaScript
                if size['width'] == 0 or size['height'] == 0:
                    try:
                        # Check if there's a data-src or other attribute with actual image URL
                        data_src = captcha_img_element.get_attribute('data-src')
                        if data_src:
                            self.driver.execute_script(f"arguments[0].src = '{data_src}';", captcha_img_element)
                            print(f"  Set src from data-src: {data_src[:50]}...")
                            time.sleep(1)

                        # Force the image to be visible and have dimensions
                        self.driver.execute_script("""
                            arguments[0].style.display = 'block';
                            arguments[0].style.visibility = 'visible';
                            arguments[0].style.width = 'auto';
                            arguments[0].style.height = 'auto';
                            arguments[0].style.minWidth = '100px';
                            arguments[0].style.minHeight = '30px';
                        """, captcha_img_element)
                        time.sleep(0.5)

                        # Re-check
                        size = captcha_img_element.size
                        print(f"  After JS fix - Size: {size}")
                    except Exception as js_err:
                        print(f"  JS fix error: {js_err}")

            # Final check
            if size['width'] == 0 or size['height'] == 0:
                print(f"CAPTCHA element still has invalid dimensions: {size}")
                # Try to get the image directly from src URL
                if img_src:
                    # Handle relative URLs
                    if img_src.startswith('/'):
                        img_src = f"https://www.ticaretsicil.gov.tr{img_src}"
                    elif not img_src.startswith('http'):
                        img_src = f"https://www.ticaretsicil.gov.tr/{img_src}"

                    print(f"  Attempting to download CAPTCHA image directly from: {img_src[:60]}...")
                    try:
                        import requests as req
                        cookies = {c['name']: c['value'] for c in self.driver.get_cookies()}
                        headers = {
                            'User-Agent': self.driver.execute_script("return navigator.userAgent;"),
                            'Referer': self.driver.current_url
                        }
                        resp = req.get(img_src, cookies=cookies, headers=headers, timeout=10)
                        if resp.status_code == 200 and len(resp.content) > 100:
                            captcha_base64 = base64.b64encode(resp.content).decode('utf-8')
                            print(f"  Downloaded CAPTCHA image ({len(resp.content)} bytes)")
                            # Skip to VLM processing with this image
                            return self._process_captcha_with_vlm(captcha_base64, model, confidence_threshold)
                        else:
                            print(f"  Download failed: status={resp.status_code}, size={len(resp.content)}")
                    except Exception as dl_err:
                        print(f"  Direct download failed: {dl_err}")
                return (None, 0.0)

            # Scroll to element to ensure it's in viewport
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", captcha_img_element)
            time.sleep(0.3)

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
            time.sleep(1)

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
                    time.sleep(1)
                else:
                    print("Warning: Could not find login button, form might already be visible")
            except Exception as e:
                print(f"Note: {str(e)}")
                print("Attempting to proceed anyway...")

            # Wait for the modal and form to appear
            print("Waiting for login form to appear...")
            time.sleep(0.5)

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
                        print("VLM confidence too low, will require manual entry...")
                except Exception as e:
                    print(f"VLM failed: {e}, will require manual entry...")
                    captcha_text = None



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
            time.sleep(1)

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

    def fetch_trade_registry_announcement(self, sicil_mudurugu, ticaret_unvani):
        """
        Navigate to the announcement page and fetch results

        Args:
            sicil_mudurugu: Name or ID of the registry office (e.g., "İSTANBUL" or "232")
            ticaret_unvani: Trade title/company name (at least first 5 characters)

        Note:
            Date filtering should be applied on the results page using filter_results_by_date()
        """
        try:
            # Store search parameters for PDF filename generation
            self.current_office = sicil_mudurugu
            self.current_company = ticaret_unvani

            print(f"\n{'='*50}")
            print("FETCHING TRADE REGISTRY ANNOUNCEMENT")
            print(f"{'='*50}")

            # Ensure we're on the main window
            try:
                if len(self.driver.window_handles) > 1:
                    # Close any extra windows
                    main_window = self.driver.window_handles[0]
                    for handle in self.driver.window_handles[1:]:
                        self.driver.switch_to.window(handle)
                        self.driver.close()
                    self.driver.switch_to.window(main_window)
                elif len(self.driver.window_handles) == 0:
                    print("Error: No browser windows available")
                    return None
            except Exception as e:
                print(f"Warning: Window management issue: {e}")

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

            time.sleep(0.5)

            # Find and fill the Trade Title (Ticaret Unvanı) field
            print(f"Entering trade title: {ticaret_unvani}")

            # Try multiple selectors to find the trade title field
            unvan_field = None
            possible_selectors = [
                (By.NAME, "TicaretUnvani"),  # The actual field name!
                (By.ID, "TicaretUnvani"),
                (By.NAME, "Unvan"),
                (By.ID, "Unvan"),
                (By.CSS_SELECTOR, "input[placeholder*='Ticaret Unvan']"),
                (By.CSS_SELECTOR, "input[type='text'][name*='Unvan']"),
            ]

            for selector_type, selector_value in possible_selectors:
                try:
                    unvan_field = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((selector_type, selector_value))
                    )
                    print(f"Found trade title field using {selector_type}: {selector_value}")
                    break
                except:
                    continue

            if not unvan_field:
                # Try to find all input fields and print them for debugging
                print("Could not find trade title field. Available input fields:")
                all_inputs = self.driver.find_elements(By.TAG_NAME, "input")
                for inp in all_inputs:
                    inp_type = inp.get_attribute('type')
                    inp_name = inp.get_attribute('name')
                    inp_id = inp.get_attribute('id')
                    inp_placeholder = inp.get_attribute('placeholder')
                    print(f"  - Type: {inp_type}, Name: {inp_name}, ID: {inp_id}, Placeholder: {inp_placeholder}")
                return None

            # Scroll to the element to ensure it's visible
            self.driver.execute_script("arguments[0].scrollIntoView(true);", unvan_field)
            time.sleep(0.5)

            # Try to interact with the field
            try:
                unvan_field.clear()
                unvan_field.send_keys(ticaret_unvani)
            except:
                # If regular interaction fails, use JavaScript
                print("Using JavaScript to fill the field...")
                self.driver.execute_script(
                    "arguments[0].value = arguments[1];",
                    unvan_field,
                    ticaret_unvani
                )
                # Trigger change event
                self.driver.execute_script(
                    "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));",
                    unvan_field
                )

            time.sleep(0.5)
            safe_print(f"✓ Successfully entered: {ticaret_unvani}")

            # Note: Date filtering will be applied on the results page, not here

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

    def filter_results_by_date(self, start_date, end_date):
        """
        Apply date filter on the results page after search

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            True if filter was applied successfully, False otherwise
        """
        try:
            print(f"\n{'='*50}")
            print("FILTERING RESULTS BY DATE")
            print(f"{'='*50}")
            print(f"Date range: {start_date} to {end_date}")

            # 1. Find and click the date checkbox on results page
            date_checkbox = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.ID, "Tarih"))
            )

            if not date_checkbox.is_selected():
                # Scroll to checkbox with offset to avoid header overlap
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", date_checkbox)
                time.sleep(0.5)

                # Use JavaScript click to avoid "element click intercepted" error
                self.driver.execute_script("arguments[0].click();", date_checkbox)
                print("✓ Date filter checkbox activated")
                time.sleep(1)  # Wait for date fields to appear

            # 2. Convert dates to Turkish format (DD.MM.YYYY)
            start_turkish = self.convert_date_format(start_date)
            end_turkish = self.convert_date_format(end_date)
            print(f"Converted dates: {start_turkish} - {end_turkish}")

            # 3. Find and fill start date field (Tarih1)
            start_date_field = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.ID, "Tarih1"))
            )
            self.driver.execute_script("arguments[0].scrollIntoView(true);", start_date_field)
            time.sleep(0.3)
            start_date_field.clear()
            start_date_field.send_keys(start_turkish)
            print(f"✓ Start date entered: {start_turkish}")

            # 4. Find and fill end date field (Tarih2)
            end_date_field = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.ID, "Tarih2"))
            )
            self.driver.execute_script("arguments[0].scrollIntoView(true);", end_date_field)
            time.sleep(0.3)
            end_date_field.clear()
            end_date_field.send_keys(end_turkish)
            print(f"✓ End date entered: {end_turkish}")

            # Wait for any dynamic UI updates after filling dates
            time.sleep(1)

            # 5. Find and click the search button to apply the filter
            print("Clicking search button to apply date filter...")
            time.sleep(0.5)

            # Try multiple selectors for the submit button (ordered by specificity)
            submit_button = None
            found_selector = None
            button_selectors = [
                # Most specific - exact match with data attribute
                (By.CSS_SELECTOR, "button[type='submit'][data-message='İlan Ara']"),
                # Specific class combinations
                (By.CSS_SELECTOR, "button.btn.c-theme-btn.c-btn-square[type='submit']"),
                (By.CSS_SELECTOR, "button.btn.c-theme-btn[type='submit']"),
                # Generic fallbacks
                (By.CSS_SELECTOR, "button.c-theme-btn[type='submit']"),
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.XPATH, "//button[@type='submit']"),
            ]

            for selector_type, selector_value in button_selectors:
                try:
                    submit_button = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((selector_type, selector_value))
                    )
                    found_selector = (selector_type, selector_value)
                    print(f"Found submit button using {selector_type}")
                    break
                except:
                    continue

            if submit_button and found_selector:
                # Get button details for debugging
                button_text = submit_button.text
                button_tag = submit_button.tag_name
                button_classes = submit_button.get_attribute('class')
                print(f"Submit button details: tag={button_tag}, text='{button_text}', classes='{button_classes}'")

                # Scroll to button
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_button)
                time.sleep(0.5)

                # Re-fetch button to avoid stale element reference
                try:
                    selector_type, selector_value = found_selector
                    submit_button = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((selector_type, selector_value))
                    )
                    print("✓ Button re-fetched and ready to click")
                except Exception as e:
                    print(f"Warning: Could not re-fetch button: {e}")

                # Make sure button is visible and enabled
                print(f"Button visible: {submit_button.is_displayed()}, enabled: {submit_button.is_enabled()}")

                # Try multiple click methods with stale element handling
                clicked = False

                # Method 1: JavaScript click (most reliable)
                try:
                    print("Attempting JavaScript click...")
                    self.driver.execute_script("arguments[0].click();", submit_button)
                    clicked = True
                    print("✓ JavaScript click successful")
                except StaleElementReferenceException:
                    print("Element became stale during click, re-fetching...")
                    try:
                        selector_type, selector_value = found_selector
                        submit_button = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((selector_type, selector_value))
                        )
                        self.driver.execute_script("arguments[0].click();", submit_button)
                        clicked = True
                        print("✓ JavaScript click successful after re-fetch")
                    except Exception as retry_error:
                        print(f"JavaScript click retry failed: {retry_error}")
                except Exception as e:
                    print(f"JavaScript click failed: {e}")

                # Method 2: Regular Selenium click (if JS failed)
                if not clicked:
                    try:
                        print("Attempting regular Selenium click...")
                        submit_button.click()
                        clicked = True
                        print("✓ Regular click successful")
                    except StaleElementReferenceException:
                        print("Element became stale, re-fetching...")
                        try:
                            selector_type, selector_value = found_selector
                            submit_button = WebDriverWait(self.driver, 3).until(
                                EC.element_to_be_clickable((selector_type, selector_value))
                            )
                            submit_button.click()
                            clicked = True
                            print("✓ Regular click successful after re-fetch")
                        except Exception as retry_error:
                            print(f"Regular click retry failed: {retry_error}")
                    except Exception as e:
                        print(f"Regular click failed: {e}")

                # Method 3: Action chains (if both failed)
                if not clicked:
                    try:
                        print("Attempting ActionChains click...")
                        from selenium.webdriver.common.action_chains import ActionChains
                        actions = ActionChains(self.driver)
                        actions.move_to_element(submit_button).click().perform()
                        clicked = True
                        print("✓ ActionChains click successful")
                    except StaleElementReferenceException:
                        print("Element became stale, re-fetching...")
                        try:
                            selector_type, selector_value = found_selector
                            submit_button = WebDriverWait(self.driver, 3).until(
                                EC.element_to_be_clickable((selector_type, selector_value))
                            )
                            actions = ActionChains(self.driver)
                            actions.move_to_element(submit_button).click().perform()
                            clicked = True
                            print("✓ ActionChains click successful after re-fetch")
                        except Exception as retry_error:
                            print(f"ActionChains click retry failed: {retry_error}")
                    except Exception as e:
                        print(f"ActionChains click failed: {e}")

                # Method 4: Coordinate-based click (last resort)
                if not clicked:
                    try:
                        print("Attempting coordinate-based click...")
                        # Get button location and size
                        location = submit_button.location
                        size = submit_button.size

                        # Calculate center coordinates
                        x = location['x'] + size['width'] / 2
                        y = location['y'] + size['height'] / 2

                        print(f"Button center coordinates: x={x:.0f}, y={y:.0f}")

                        # Use ActionChains to move to coordinates and click
                        from selenium.webdriver.common.action_chains import ActionChains
                        actions = ActionChains(self.driver)

                        # Move to the button's center coordinates and click
                        actions.move_to_element_with_offset(submit_button, 0, 0).click().perform()
                        clicked = True
                        print("✓ Coordinate-based click successful")
                    except StaleElementReferenceException:
                        print("Element became stale, re-fetching...")
                        try:
                            selector_type, selector_value = found_selector
                            submit_button = WebDriverWait(self.driver, 3).until(
                                EC.element_to_be_clickable((selector_type, selector_value))
                            )
                            location = submit_button.location
                            size = submit_button.size
                            x = location['x'] + size['width'] / 2
                            y = location['y'] + size['height'] / 2
                            print(f"Button center coordinates: x={x:.0f}, y={y:.0f}")
                            actions = ActionChains(self.driver)
                            actions.move_to_element_with_offset(submit_button, 0, 0).click().perform()
                            clicked = True
                            print("✓ Coordinate-based click successful after re-fetch")
                        except Exception as retry_error:
                            print(f"Coordinate-based click retry failed: {retry_error}")
                    except Exception as e:
                        print(f"Coordinate-based click failed: {e}")

                if clicked:
                    print("✓ Search button clicked successfully")
                    # Wait for filtered results to load
                    time.sleep(3)
                else:
                    print("✗ All click methods failed")
            else:
                print("Warning: Could not find submit button, filter might not be applied")

            safe_print(f"✓ Date filter applied: {start_turkish} - {end_turkish}")
            return True

        except Exception as e:
            print(f"Warning: Could not apply date filter: {e}")
            import traceback
            traceback.print_exc()
            return False

    def solve_pdf_captcha(self, timeout=5):
        """
        Check if CAPTCHA appears during PDF download and solve it using VLM

        Args:
            timeout: Max time to wait for CAPTCHA form (default: 5 seconds)

        Returns:
            True if CAPTCHA was solved or not present, False if failed
        """
        try:
            # Check if CAPTCHA form is present
            try:
                WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.ID, "FormGuvenlikKodu"))
                )
                print("CAPTCHA detected during PDF download, solving...")
            except TimeoutException:
                # No CAPTCHA, proceed normally
                return True

            # Try to solve CAPTCHA with VLM
            captcha_text, confidence = self.solve_captcha_with_vlm()

            if not captcha_text or confidence < 0.6:
                print(f"VLM CAPTCHA solving failed (confidence: {confidence:.2f})")
                return False

            safe_print(f"✓ VLM solved PDF CAPTCHA: '{captcha_text}' (confidence: {confidence:.2f})")

            # Find and fill the CAPTCHA field (note: different ID than login)
            captcha_field = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.ID, "CaptchaIlan"))
            )

            captcha_field.clear()
            captcha_field.send_keys(captcha_text)
            time.sleep(0.5)

            # Submit the form
            submit_button = self.driver.find_element(By.CSS_SELECTOR, "#FormGuvenlikKodu button[type='submit']")
            submit_button.click()

            # Wait for form to be submitted and page to load
            time.sleep(2)

            safe_print("✓ PDF CAPTCHA submitted successfully")
            return True

        except Exception as e:
            print(f"Error solving PDF CAPTCHA: {e}")
            import traceback
            traceback.print_exc()
            return False

    def extract_pdf_metadata_from_table(self):
        """
        Extract metadata (date, issue, page) for each PDF from the results table

        Returns:
            List of dictionaries containing metadata for each row, or empty list if failed
        """
        try:
            print("\nExtracting metadata from results table...")

            # Find the results table
            table = self.driver.find_element(By.ID, "tblIlanGoruntuleme")

            # Find all rows in the table body
            rows = table.find_elements(By.CSS_SELECTOR, "tbody tr")

            metadata_list = []

            for row_idx, row in enumerate(rows, 1):
                try:
                    # Get all cells in the row
                    cells = row.find_elements(By.TAG_NAME, "td")

                    if len(cells) < 4:
                        print(f"  Row {row_idx}: Not enough cells, skipping")
                        continue

                    # Extract data from cells (adjust indices based on table structure)
                    # Typically: [PDF link, Date, Issue, Page, ...]
                    # You may need to adjust these indices based on the actual table structure

                    # Try to find the PDF link in this row
                    pdf_link_element = row.find_element(By.CSS_SELECTOR, "a[href*='pdf_goster.php']")
                    pdf_url = pdf_link_element.get_attribute('href')

                    # Extract text from cells
                    # The exact column indices may vary - adjust as needed
                    yayin_tarihi = ""  # Publication date
                    sayi = ""  # Issue number
                    sayfa = ""  # Page number

                    # Try to find cells by their content or position
                    for cell in cells:
                        cell_text = cell.text.strip()
                        # Date format is typically DD.MM.YYYY
                        if '.' in cell_text and len(cell_text) == 10:
                            yayin_tarihi = cell_text
                        # Issue and page are typically numbers
                        elif cell_text.isdigit():
                            if not sayi:
                                sayi = cell_text
                            elif not sayfa:
                                sayfa = cell_text

                    metadata = {
                        'url': pdf_url,
                        'yayin_tarihi': yayin_tarihi,
                        'sayi': sayi,
                        'sayfa': sayfa,
                        'row_index': row_idx
                    }

                    metadata_list.append(metadata)
                    print(f"  Row {row_idx}: Date={yayin_tarihi}, Issue={sayi}, Page={sayfa}")

                except Exception as e:
                    print(f"  Row {row_idx}: Error extracting metadata - {e}")
                    continue

            print(f"✓ Extracted metadata for {len(metadata_list)} PDF(s)")
            return metadata_list

        except Exception as e:
            print(f"Error extracting table metadata: {e}")
            import traceback
            traceback.print_exc()
            return []

    def set_items_per_page(self, count=100):
        """
        Set the number of items displayed per page in results table

        Args:
            count: Number of items per page (10, 25, 50, or 100)

        Returns:
            True if successful, False otherwise
        """
        try:
            from selenium.webdriver.support.ui import Select

            select_element = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.NAME, "tblIlanGoruntuleme_length"))
            )
            select = Select(select_element)
            select.select_by_value(str(count))

            # Wait for table to refresh
            time.sleep(2)
            print(f"Set items per page to {count}")
            return True
        except Exception as e:
            print(f"Could not set items per page: {e}")
            return False

    def has_next_page(self):
        """
        Check if there's a next page available in pagination

        Returns:
            True if next page exists and is clickable, False otherwise
        """
        try:
            next_button = self.driver.find_element(By.ID, "tblIlanGoruntuleme_next")
            # Check if button is disabled (has "disabled" class)
            classes = next_button.get_attribute("class") or ""
            return "disabled" not in classes
        except:
            return False

    def go_to_next_page(self):
        """
        Navigate to the next page of results

        Returns:
            True if navigation successful, False otherwise
        """
        try:
            next_button = self.driver.find_element(By.ID, "tblIlanGoruntuleme_next")
            next_link = next_button.find_element(By.TAG_NAME, "a")

            self.driver.execute_script("arguments[0].click();", next_link)
            time.sleep(2)  # Wait for table to update

            print("Navigated to next page")
            return True
        except Exception as e:
            print(f"Could not navigate to next page: {e}")
            return False

    def collect_pdf_urls_from_current_page(self):
        """
        Collect all PDF URLs from the current results page

        Returns:
            List of PDF URLs found on current page
        """
        pdf_urls = []

        # Look for PDF links
        pdf_link_selectors = [
            (By.CSS_SELECTOR, "a[href*='pdf_goster.php']"),
            (By.CSS_SELECTOR, "a[href*='.pdf']"),
        ]

        for selector_type, selector_value in pdf_link_selectors:
            try:
                links = self.driver.find_elements(selector_type, selector_value)
                for link in links:
                    try:
                        href = link.get_attribute('href')
                        if href and href not in pdf_urls:
                            if href.startswith('/'):
                                href = f"https://www.ticaretsicil.gov.tr{href}"
                            pdf_urls.append(href)
                    except:
                        continue
            except:
                continue

        return pdf_urls

    def collect_all_pdf_urls(self):
        """
        Collect PDF URLs from all pages of results by iterating through pagination

        Returns:
            List of all unique PDF URLs across all pages
        """
        all_pdf_urls = []
        page_num = 1

        # First, set items per page to maximum (100) to minimize pagination
        self.set_items_per_page(100)

        # Collect from first page
        print(f"Collecting PDFs from page {page_num}...")
        urls = self.collect_pdf_urls_from_current_page()
        all_pdf_urls.extend(urls)
        print(f"  Found {len(urls)} PDF(s) on page {page_num}")

        # Iterate through remaining pages
        while self.has_next_page():
            page_num += 1
            if not self.go_to_next_page():
                break

            print(f"Collecting PDFs from page {page_num}...")
            urls = self.collect_pdf_urls_from_current_page()
            all_pdf_urls.extend(urls)
            print(f"  Found {len(urls)} PDF(s) on page {page_num}")

        # Deduplicate while preserving order
        unique_urls = list(dict.fromkeys(all_pdf_urls))
        print(f"\nTotal: {len(unique_urls)} unique PDF(s) across {page_num} page(s)")

        return unique_urls

    def _extract_pdf_url_from_page(self):
        """
        Extract the actual PDF URL from embed/iframe elements on the current page

        Returns:
            PDF URL string or None if not found
        """
        final_pdf_url = None

        # Look for PDF in embed tag
        try:
            embed = self.driver.find_element(By.CSS_SELECTOR, "embed[type='application/pdf'], embed[src*='.pdf'], embed[src*='tmp_gazete']")
            final_pdf_url = embed.get_attribute('src')
            print(f"Found PDF in embed: ...{final_pdf_url[-60:]}")
        except:
            pass

        # Look for PDF in iframe tag if not found in embed
        if not final_pdf_url:
            try:
                iframe = self.driver.find_element(By.CSS_SELECTOR, "iframe[src*='.pdf'], iframe[src*='tmp_gazete']")
                final_pdf_url = iframe.get_attribute('src')
                print(f"Found PDF in iframe: ...{final_pdf_url[-60:]}")
            except:
                pass

        # Look for object tag as another fallback
        if not final_pdf_url:
            try:
                obj = self.driver.find_element(By.CSS_SELECTOR, "object[type='application/pdf'], object[data*='.pdf']")
                final_pdf_url = obj.get_attribute('data')
                print(f"Found PDF in object: ...{final_pdf_url[-60:]}")
            except:
                pass

        # If still not found, check current URL as last resort
        if not final_pdf_url:
            current = self.driver.current_url
            # Only use current URL if it looks like a PDF path
            if 'tmp_gazete' in current or current.endswith('.pdf'):
                final_pdf_url = current
                print(f"Using current URL: ...{final_pdf_url[-60:]}")
            else:
                print(f"Current URL is not a PDF: ...{current[-60:]}")

        # Make URL absolute if needed
        if final_pdf_url and final_pdf_url.startswith('/'):
            final_pdf_url = f"https://www.ticaretsicil.gov.tr{final_pdf_url}"

        # Validate URL is a PDF, not a CAPTCHA or viewer page
        if final_pdf_url:
            if 'pdf_goster.php' in final_pdf_url and 'tmp_gazete' not in final_pdf_url:
                print(f"Warning: URL is viewer page, not actual PDF - may need CAPTCHA")
                return None
            if 'guvenlik' in final_pdf_url.lower() or 'captcha' in final_pdf_url.lower():
                print(f"Warning: URL appears to be CAPTCHA page")
                return None

        return final_pdf_url

    def download_pdf_with_requests(self, url, output_path):
        """
        Download a PDF file using requests library with session cookies from Selenium

        Args:
            url: URL of the PDF to download
            output_path: Path where the PDF should be saved

        Returns:
            True if download succeeded, False otherwise
        """
        try:
            # Get cookies from Selenium session
            selenium_cookies = self.driver.get_cookies()

            # Create a requests session and add the cookies
            session = requests.Session()
            for cookie in selenium_cookies:
                session.cookies.set(cookie['name'], cookie['value'])

            # Set headers to mimic browser request
            headers = {
                'User-Agent': self.driver.execute_script("return navigator.userAgent;"),
                'Referer': self.driver.current_url
            }

            # Download the PDF
            response = session.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            # Check if response is actually a PDF
            content_type = response.headers.get('content-type', '')
            if 'application/pdf' not in content_type.lower():
                print(f"Warning: Content type is '{content_type}', expected PDF")
                # Still try to save it

            # Save the PDF
            with open(output_path, 'wb') as f:
                f.write(response.content)

            # Verify file was written and has content
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True
            else:
                print(f"File was not written properly: {output_path}")
                return False

        except requests.exceptions.RequestException as e:
            print(f"Request error downloading PDF: {e}")
            return False
        except Exception as e:
            print(f"Error downloading PDF: {e}")
            import traceback
            traceback.print_exc()
            return False

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

            # Find ALL PDF links/embeds in results
            print("Looking for PDFs in results...")
            print(f"Current URL: {self.driver.current_url}")

            # Save page source for debugging
            try:
                debug_html_path = os.path.join(self.pdf_output_dir, "debug_page_source.html")
                with open(debug_html_path, 'w', encoding='utf-8') as f:
                    f.write(self.driver.page_source)
                print(f"✓ Saved page source to: {debug_html_path}")
            except Exception as e:
                print(f"Could not save page source: {e}")

            # Collect PDF URLs from all pages (handles pagination automatically)
            try:
                pdf_urls = self.collect_all_pdf_urls()

                if not pdf_urls:
                    print("\n" + "="*50)
                    print("NO PDFs FOUND IN SEARCH RESULTS")
                    print("="*50)
                    print("Possible reasons:")
                    print("1. No results match your search criteria")
                    print("2. Results page structure has changed")
                    print(f"3. Check the saved HTML: {debug_html_path}")
                    print("="*50 + "\n")

                    # Take a screenshot for debugging
                    try:
                        screenshot_path = os.path.join(self.pdf_output_dir, "debug_no_pdfs.png")
                        self.driver.save_screenshot(screenshot_path)
                        print(f"Saved screenshot to: {screenshot_path}")
                    except Exception as e:
                        print(f"Could not save screenshot: {e}")

                    return []

            except Exception as e:
                print(f"Could not find PDFs: {e}")
                import traceback
                traceback.print_exc()
                return []

            # Limit to max_pdfs if specified
            if max_pdfs and max_pdfs < len(pdf_urls):
                print(f"Limiting to {max_pdfs} most recent PDF(s)")
                pdf_urls = pdf_urls[:max_pdfs]

            # Show all URLs for debugging
            for idx, url in enumerate(pdf_urls, 1):
                print(f"  PDF {idx}: ...{url[-60:]}")  # Show last 60 chars to see GUID

            # Extract metadata from table
            metadata_list = self.extract_pdf_metadata_from_table()

            # Create a mapping from PDF URL to metadata
            url_to_metadata = {}
            for metadata in metadata_list:
                url_to_metadata[metadata['url']] = metadata

            # Get list of existing files before downloading
            existing_files = set()
            if os.path.exists(self.pdf_output_dir):
                existing_files = set(os.listdir(self.pdf_output_dir))

            # Download each PDF by navigating to it in a new tab
            downloaded_files = []

            for idx, pdf_url in enumerate(pdf_urls, 1):
                try:
                    print(f"\nDownloading PDF {idx}/{len(pdf_urls)}...")

                    # Get metadata for this PDF before opening (match by original URL)
                    metadata = url_to_metadata.get(pdf_url, {})

                    # Check for CAPTCHA by opening URL in new tab first
                    print("Checking for CAPTCHA (waiting up to 5 seconds)...")
                    self.driver.execute_script(f"window.open('{pdf_url}', '_blank');")
                    self.driver.switch_to.window(self.driver.window_handles[-1])
                    time.sleep(1)  # Initial page load

                    # Wait for CAPTCHA to potentially appear (delayed CAPTCHA detection)
                    captcha_detected = False
                    try:
                        WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.ID, "FormGuvenlikKodu"))
                        )
                        captcha_detected = True
                        print("CAPTCHA detected, solving...")
                    except TimeoutException:
                        print("No CAPTCHA required for this PDF")

                    # If CAPTCHA was detected, solve it with retry loop
                    if captcha_detected:
                        max_captcha_attempts = 3
                        captcha_success = False

                        for captcha_attempt in range(max_captcha_attempts):
                            captcha_solved = self.solve_pdf_captcha(timeout=3)

                            if not captcha_solved:
                                print(f"✗ CAPTCHA attempt {captcha_attempt + 1} failed")
                                break

                            # After solving CAPTCHA, navigate back to PDF URL
                            print(f"CAPTCHA solved, navigating to PDF URL (attempt {captcha_attempt + 1})...")
                            self.driver.get(pdf_url)
                            time.sleep(3)  # Wait for page to load

                            # Check if another CAPTCHA appeared
                            try:
                                WebDriverWait(self.driver, 3).until(
                                    EC.presence_of_element_located((By.ID, "FormGuvenlikKodu"))
                                )
                                print("Another CAPTCHA detected, solving again...")
                                continue  # Loop back to solve again
                            except TimeoutException:
                                # No more CAPTCHA, success!
                                captcha_success = True
                                break

                        if not captcha_success:
                            print(f"✗ PDF {idx}: CAPTCHA solving failed after {max_captcha_attempts} attempts, skipping...")
                            self.driver.close()
                            self.driver.switch_to.window(original_window)
                            continue

                    # Extract the actual PDF URL (works for both CAPTCHA and non-CAPTCHA cases)
                    final_pdf_url = self._extract_pdf_url_from_page()

                    if not final_pdf_url:
                        print(f"✗ PDF {idx}: Could not find PDF URL on page")
                        self.driver.close()
                        self.driver.switch_to.window(original_window)
                        continue

                    # Close the tab and switch back
                    self.driver.close()
                    self.driver.switch_to.window(original_window)

                    # Generate filename from metadata
                    if metadata and metadata.get('yayin_tarihi'):
                        # Clean values for safe filename
                        company = (self.current_company or "unknown").replace(' ', '_').replace('/', '_').replace('\\', '_')
                        office = (self.current_office or "unknown").replace(' ', '_').replace('/', '_').replace('\\', '_')
                        date = metadata.get('yayin_tarihi', '').replace('.', '_')
                        issue = metadata.get('sayi', 'unknown')
                        page = metadata.get('sayfa', 'unknown')

                        # Format: company_office_date_issue_page.pdf
                        new_filename = f"{company}_{office}_{date}_{issue}_{page}.pdf"
                    else:
                        # Fallback to simple naming if metadata not found
                        new_filename = f"gazette_{idx}.pdf"

                    new_filepath = os.path.join(self.pdf_output_dir, new_filename)

                    # If file already exists with this name, remove it
                    if os.path.exists(new_filepath):
                        os.remove(new_filepath)

                    # Download the PDF
                    if self.download_pdf_with_requests(final_pdf_url, new_filepath):
                        file_size = os.path.getsize(new_filepath) / 1024  # KB
                        safe_print(f"✓ PDF {idx} downloaded: {new_filename} ({file_size:.1f} KB)")
                        downloaded_files.append(new_filepath)
                        existing_files.add(new_filename)
                    else:
                        print(f"✗ PDF {idx}: Download failed")

                except Exception as e:
                    print(f"✗ PDF {idx}: Error - {e}")
                    import traceback
                    traceback.print_exc()
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
  python ticaret_sicil_scraper.py --office ANKARA --title "TURKCELL"

  # With date range
  python ticaret_sicil_scraper.py --office ANKARA --title "TURKCELL" \\
      --start-date 2024-01-01 --end-date 2024-12-31

  # Download PDF from results
  python ticaret_sicil_scraper.py --office ANKARA --title "TURKCELL" --download-pdf

  # Download only the 2 most recent PDFs
  python ticaret_sicil_scraper.py --office ANKARA --title "TURKCELL" --download-pdf --max-pdfs 2

  # Full featured: date range + PDF download
  python ticaret_sicil_scraper.py --office ANKARA --title "TURKCELL" \\
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
    parser.add_argument('--title', type=str,
                        help='Trade title/company name - at least first 5 characters (e.g., "TURKCELL")')

    # Optional date filtering
    parser.add_argument('--start-date', type=str,
                        help='Start date for filtering (YYYY-MM-DD format)')
    parser.add_argument('--end-date', type=str,
                        help='End date for filtering (YYYY-MM-DD format)')

    # CAPTCHA options
    parser.add_argument('--no-vlm', action='store_true',
                        help='Skip VLM CAPTCHA solving, use manual entry only')

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
        # In non-interactive mode, --office and --title are required
        if not args.office or not args.title:
            parser.error("--office and --title are required (or use --interactive for legacy mode)")

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

    if not EMAIL or not PASSWORD:
        print("Error: EMAIL and PASSWORD must be set in .env file")
        print("Please create a .env file with:")
        print("EMAIL=your_email@example.com")
        print("PASSWORD=your_password")
        return


    # Create login instance
    login = TicaretSicilLogin(EMAIL, PASSWORD, args.pdf_output_dir)

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

                    # Get trade title
                    print("Enter Ticaret Unvanı (at least first 5 characters): ", end='')
                    ticaret_unvani = input().strip()

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
                ticaret_unvani = args.title
                start_date = args.start_date
                end_date = args.end_date

                print(f"Registry Office: {sicil_mudurugu}")
                print(f"Trade Title: {ticaret_unvani}")
                if start_date and end_date:
                    print(f"Date Range: {start_date} to {end_date}")

            if fetch_choice == 'y':
                # Fetch the announcement
                page_source = login.fetch_trade_registry_announcement(
                    sicil_mudurugu,
                    ticaret_unvani
                )

                if page_source:
                    # Apply date filter on results page if dates were provided
                    if start_date and end_date:
                        login.filter_results_by_date(start_date, end_date)

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
