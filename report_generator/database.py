"""
KKB Hackathon - Database Connection Manager
PostgreSQL veritabanı bağlantı yönetimi
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional
from contextlib import contextmanager

from config import DB_CONFIG, USE_MOCK_DATA


class DatabaseManager:
    """PostgreSQL veritabanı bağlantı yöneticisi"""
    
    def __init__(self):
        self.config = DB_CONFIG
        self._connection = None
    
    def get_connection(self):
        """Veritabanı bağlantısı oluşturur"""
        if USE_MOCK_DATA:
            print("⚠️  Mock data modu aktif - Veritabanı bağlantısı atlanıyor")
            return None
        
        try:
            conn = psycopg2.connect(**self.config)
            print("✅ Veritabanı bağlantısı başarılı")
            return conn
        except Exception as e:
            print(f"❌ Veritabanı bağlantı hatası: {e}")
            raise
    
    @contextmanager
    def get_cursor(self):
        """Context manager ile cursor yönetimi"""
        conn = self.get_connection()
        if conn is None:
            yield None
            return
        
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()
    
    def execute_query(self, query: str, params: tuple = None):
        """SQL sorgusu çalıştırır ve sonuçları döner"""
        with self.get_cursor() as cursor:
            if cursor is None:
                return []
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            return [dict(row) for row in results]
    
    def test_connection(self) -> bool:
        """Veritabanı bağlantısını test eder"""
        if USE_MOCK_DATA:
            print("⚠️  Mock data modunda test atlanıyor")
            return True
        
        try:
            conn = self.get_connection()
            conn.close()
            return True
        except:
            return False


# Global database manager instance
db_manager = DatabaseManager()
