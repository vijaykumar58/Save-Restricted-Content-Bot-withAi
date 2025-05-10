from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
import base64
import os
import warnings
from config import MASTER_KEY, IV_KEY

# Constants
SALT_LENGTH = 16
ITERATIONS = 480000  # Updated from 100k to 480k (OWASP 2023 recommendation)
KEY_LENGTH = 32  # Using 256-bit keys for AES

def derive_key(password: str = MASTER_KEY, salt: str = IV_KEY, key_length: int = KEY_LENGTH) -> bytes:
    """
    Derive a cryptographic key from a password using PBKDF2-HMAC-SHA256.
    
    Args:
        password: The master password (default from config)
        salt: Cryptographic salt (default from config)
        key_length: Desired key length in bytes
        
    Returns:
        Derived key as bytes
    """
    if len(salt) < 8:
        warnings.warn("Salt is too short (minimum 8 bytes recommended)", UserWarning)
        
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=key_length,
        salt=salt.encode(),
        iterations=ITERATIONS,
        backend=default_backend()
    )
    return kdf.derive(password.encode())

def encrypt_string(plaintext: str) -> str:
    """
    Encrypt a string using AES-GCM authenticated encryption.
    
    Args:
        plaintext: String to encrypt
        
    Returns:
        Base64 encoded string containing nonce + tag + ciphertext
    """
    key = derive_key()
    nonce = os.urandom(12)  # 96-bit nonce for GCM
    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce), backend=default_backend())
    encryptor = cipher.encryptor()
    
    ciphertext = encryptor.update(plaintext.encode()) + encryptor.finalize()
    tag = encryptor.tag
    
    # Structure: nonce (12) + tag (16) + ciphertext
    encrypted_data = nonce + tag + ciphertext
    return base64.b64encode(encrypted_data).decode('utf-8')

def decrypt_string(encrypted_data: str) -> str:
    """
    Decrypt a string encrypted with encrypt_string().
    
    Args:
        encrypted_data: Base64 encoded encrypted string
        
    Returns:
        Decrypted plaintext string
        
    Raises:
        ValueError: If authentication fails or data is corrupted
    """
    try:
        key = derive_key()
        decoded_data = base64.b64decode(encrypted_data.encode('utf-8'))
        
        nonce = decoded_data[:12]
        tag = decoded_data[12:28]
        ciphertext = decoded_data[28:]
        
        cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag), backend=default_backend())
        decryptor = cipher.decryptor()
        
        plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        return plaintext.decode('utf-8')
    except Exception as e:
        raise ValueError("Decryption failed - possible tampering or invalid key") from e

# Maintain original function names for backward compatibility
dyk = derive_key
ecs = encrypt_string
dcs = decrypt_string