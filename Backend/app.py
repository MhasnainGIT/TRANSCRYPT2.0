# Standard library imports
import os
import uuid
import time
import json
import random
import traceback
import io
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from functools import wraps

# Third-party imports
import firebase_admin
import requests
import segno
from flask import Flask, request, jsonify, send_file, make_response
from flask_cors import CORS
from firebase_admin import credentials, firestore, auth
from stellar_sdk import Server, Keypair, Network, TransactionBuilder, Asset, exceptions
from dotenv import load_dotenv
from bitcoinlib.wallets import Wallet
from eth_account import Account

# Load environment variables
load_dotenv()

# Import utility functions
try:
    from util_wallet import (
        calculate_crypto_amounts, 
        get_crypto_data, 
        keep_payment, 
        calculate_inr_balances, 
        get_stellar_balance, 
        send_payment_and_show_balances, 
        get_exchange_rate, 
        get_crypto_price_in_inr
    )
except ImportError as e:
    print(f"Warning: Could not import wallet utilities: {e}")
    # Define dummy functions if import fails
    def calculate_crypto_amounts(*args, **kwargs):
        return 0
    def get_crypto_data(*args, **kwargs):
        return {}
    def keep_payment(*args, **kwargs):
        return {"success": False, "error": "Wallet utilities not available"}
    def calculate_inr_balances(*args, **kwargs):
        return 0
    def get_stellar_balance(*args, **kwargs):
        return 0
    def send_payment_and_show_balances(*args, **kwargs):
        return {"success": False, "error": "Wallet utilities not available"}
    def get_exchange_rate(*args, **kwargs):
        return 0
    def get_crypto_price_in_inr(*args, **kwargs):
        return 0

# Initialize Flask app
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Configuration
app.config['STELLAR_NETWORK'] = os.getenv('STELLAR_NETWORK', 'testnet')  # or 'public' for mainnet
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
app.config['MONGODB_URI'] = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/transcrypt')
app.config['ADMIN_RECEIVER_KEY'] = os.getenv('ADMIN_RECEIVER_KEY')

# Initialize Firebase
db = None
firebase_app = None
try:
    # Try to find the service account key in the current directory
    cred_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'serviceAccountKey.json')
    print(f"Loading Firebase credentials from: {cred_path}")
    
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_app = firebase_admin.initialize_app(cred, {
            'projectId': 'transcrypt-41b4d',
        })
        db = firestore.client()
        print("Successfully initialized Firebase Admin")
    else:
        print("Warning: Firebase credentials not found. Running in limited mode.")
except Exception as e:
    print(f"Error initializing Firebase: {str(e)}")
    print(traceback.format_exc())
    db = None

# Stellar Helper Functions
def get_stellar_server():
    """Get the appropriate Stellar server based on network"""
    network = app.config.get('STELLAR_NETWORK', 'testnet')
    if network == 'testnet':
        return Server(horizon_url="https://horizon-testnet.stellar.org")
    return Server(horizon_url="https://horizon.stellar.org")

def is_valid_stellar_address(address):
    """Check if a Stellar address is valid"""
    if not address or not isinstance(address, str):
        return False
    return address.startswith('G') and len(address) == 56

def get_stellar_network_passphrase():
    """Get the appropriate network passphrase"""
    network = app.config.get('STELLAR_NETWORK', 'testnet')
    if network == 'testnet':
        return Network.TESTNET_NETWORK_PASSPHRASE
    return Network.PUBLIC_NETWORK_PASSPHRASE

def require_auth(f):
    """Decorator to require authentication for protected routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Missing or invalid authorization token"}), 401
        
        token = auth_header.split(' ')[1]
        try:
            if not firebase_app:
                raise Exception("Firebase not initialized")
            decoded_token = auth.verify_id_token(token)
            request.user = decoded_token
        except Exception as e:
            print(f"Auth error: {str(e)}")
            return jsonify({"error": "Invalid or expired token"}), 401
            
        return f(*args, **kwargs)
    return decorated_function

# Initialize Stellar server and network passphrase
try:
    server = get_stellar_server()
    network_passphrase = get_stellar_network_passphrase()
    print(f"Initialized Stellar {app.config['STELLAR_NETWORK']} network")
except Exception as e:
    print(f"Error initializing Stellar: {str(e)}")
    print(traceback.format_exc())
    server = None
    network_passphrase = None

# Helper functions
def get_account_safe(public_key):
    """Safely get account information from the Stellar network"""
    if not is_valid_stellar_address(public_key):
        return None
        
    try:
        return server.accounts().account_id(public_key).call()
    except Exception as e:
        if hasattr(e, 'status') and e.status == 404:
            print(f"Account {public_key} not found on the network")
        else:
            print(f"Error checking account {public_key}: {str(e)}")
        return None

def is_account_funded(public_key):
    """Check if a Stellar account exists and is funded"""
    account = get_account_safe(public_key)
    if not account:
        return False
        
    # Check if account has any balance
    balances = account.get('balances', [])
    if not balances:
        print(f"Account {public_key} exists but has no balance")
        return False
        
    # Check if any balance is positive
    for bal in balances:
        if float(bal.get('balance', 0)) > 0:
            return True
    
    print(f"Account {public_key} exists but has zero balance")
    return False

def fund_stellar_account(public_key, max_retries=3, initial_delay=1):
    """
    Fund a Stellar testnet account using friendbot with retry logic
    
    Args:
        public_key (str): The Stellar public key to fund
        max_retries (int): Maximum number of retry attempts (default: 3)
        initial_delay (float): Initial delay between retries in seconds (default: 1)
        
    Returns:
        dict: {
            'success': bool,
            'message': str,
            'attempts': int,
            'funded': bool,
            'error': str (if any)
        }
    """
    if not is_valid_stellar_address(public_key):
        error_msg = f"Invalid Stellar public key: {public_key}"
        print(error_msg)
        return {
            'success': False,
            'message': error_msg,
            'attempts': 0,
            'funded': False,
            'error': 'INVALID_PUBLIC_KEY'
        }
    
    # Check if account is already funded
    if is_account_funded(public_key):
        msg = f"Account {public_key} is already funded"
        print(msg)
        return {
            'success': True,
            'message': msg,
            'attempts': 0,
            'funded': True,
            'error': None
        }
    
    print(f"Funding account {public_key} on testnet...")
    
    delay = initial_delay
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Use friendbot to fund the account
            response = requests.get(
                f"https://friendbot.stellar.org?addr={public_key}",
                timeout=10
            )
            response.raise_for_status()
            
            # Give the network a moment to update
            time.sleep(2)
            
            # Verify the account was actually funded
            if is_account_funded(public_key):
                msg = f"Successfully funded account {public_key} on attempt {attempt + 1}"
                print(msg)
                return {
                    'success': True,
                    'message': msg,
                    'attempts': attempt + 1,
                    'funded': True,
                    'error': None
                }
                
            last_error = f"Friendbot succeeded but account {public_key} is still not funded"
            print(last_error)
            
        except requests.exceptions.HTTPError as e:
            last_error = f"HTTP error: {str(e)}"
            print(f"Attempt {attempt + 1} failed: {last_error}")
        except requests.exceptions.RequestException as e:
            last_error = f"Request failed: {str(e)}"
            print(f"Attempt {attempt + 1} failed: {last_error}")
        except Exception as e:
            last_error = f"Unexpected error: {str(e)}"
            print(f"Attempt {attempt + 1} failed: {last_error}")
        
        # Exponential backoff with jitter
        if attempt < max_retries - 1:
            sleep_time = delay * (2 ** attempt) * (0.5 + random.random())
            print(f"Retrying in {sleep_time:.2f} seconds...")
            time.sleep(sleep_time)
    
    # If we get here, all attempts failed
    error_msg = f"Failed to fund account {public_key} after {max_retries} attempts"
    if last_error:
        error_msg += f": {last_error}"
    print(error_msg)
    
    return {
        'success': False,
        'message': error_msg,
        'attempts': max_retries,
        'funded': False,
        'error': 'FUNDING_FAILED'
    }

def authenticate(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        data = request.get_json() or {}
        email = data.get('email') or request.args.get('email')
        password = data.get('password') or request.args.get('password')
        
        if not email or not password:
            return jsonify({"error": "Email and password are required"}), 400

        try:
            if not db:
                return jsonify({"error": "Database not initialized"}), 500
                
            user_query = db.collection('wallets').where('email', '==', email).limit(1).stream()
            user_doc = next(user_query, None)
            
            if not user_doc:
                return jsonify({"error": "User not found"}), 404

            user_data = user_doc.to_dict()
            if user_data.get('password') != password:
                return jsonify({"error": "Invalid credentials"}), 401

            request.user = user_data
            request.user_id = user_doc.id
            return f(*args, **kwargs)

        except Exception as e:
            return jsonify({"error": f"Authentication failed: {str(e)}"}), 500
    return decorated_function

# Debug Endpoints
@app.route('/api/debug/firebase-status', methods=['GET'])
def check_firebase():
    try:
        if not db:
            return jsonify({"status": "error", "message": "Firebase not initialized"}), 500
            
        # Test Firestore connection
        test_doc = db.collection('test').document('connection_test')
        test_doc.set({'timestamp': firestore.SERVER_TIMESTAMP})
        test_doc.delete()
        
        return jsonify({
            "status": "success",
            "message": "Firebase connection is working",
            "collections": [coll.id for coll in db.collections()] if db else "No DB connection"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
            "service_account": os.getenv('GOOGLE_APPLICATION_CREDENTIALS'),
            "current_dir": os.getcwd()
        }), 500

@app.route('/api/debug/env', methods=['GET'])
def show_env():
    return jsonify({
        'GOOGLE_APPLICATION_CREDENTIALS': os.getenv('GOOGLE_APPLICATION_CREDENTIALS'),
        'FIREBASE_PROJECT_ID': os.getenv('FIREBASE_PROJECT_ID'),
        'FIREBASE_STORAGE_BUCKET': os.getenv('FIREBASE_STORAGE_BUCKET'),
        'current_working_directory': os.getcwd(),
        'files_in_directory': os.listdir('.')
    })

# Application routes
@app.route('/')
def index():
    return jsonify({"message": "Welcome to the Stellar Wallet API!"})

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "ok", 
        "network": app.config['STELLAR_NETWORK'],
        "firebase_connected": bool(db)
    })

@app.route('/api/wallet/create', methods=['POST'])
def create_wallet():
    try:
        data = request.get_json()
        name = data.get('name')
        email = data.get('email')
        password = data.get('password')

        if not all([name, email, password]):
            return jsonify({'error': 'Name, email, and password are required'}), 400

        # Check if email exists
        existing_user = list(db.collection('wallets').where('email', '==', email).limit(1).stream())
        if existing_user:
            return jsonify({'error': 'Email already registered'}), 409

        # Create wallet data structure
        wallet_data = {
            'name': name,
            'email': email,
            'password': password,
            'wallet_addresses': {},
            'wallet_secrets': {},
            'inr_balance': 10000.0,  # Starting balance for INR
            'created_at': firestore.SERVER_TIMESTAMP
        }

        # Create wallets for each cryptocurrency
        funding_results = {}
        for currency in ['btc', 'eth', 'sol']:
            try:
                # Generate keypair for the currency
                keypair = Keypair.random()
                public_key = keypair.public_key
                secret_key = keypair.secret
                
                # Store wallet info
                wallet_data['wallet_addresses'][currency] = public_key
                wallet_data['wallet_secrets'][currency] = secret_key
                
                # Attempt to fund the account
                funding_success = fund_stellar_account(public_key)
                funding_results[currency] = {
                    'public_key': public_key,
                    'funded': funding_success,
                    'message': 'Account funded successfully' if funding_success 
                              else 'Account created but funding failed. Use /api/wallet/fund-account to fund it.'
                }
                
                if not funding_success:
                    print(f"Warning: Failed to fund {currency.upper()} wallet for {email}")

            except Exception as e:
                error_msg = f"Error creating {currency} wallet: {str(e)}"
                print(error_msg)
                funding_results[currency] = {
                    'error': error_msg,
                    'funded': False
                }

        # Create INR wallet
        wallet_data['wallet_addresses']['inr'] = f"inr_wallet_{email.replace('@', '_at_')}"
        
        # Save to Firestore
        wallet_ref = db.collection('wallets').document()
        wallet_ref.set(wallet_data)
        
        # Prepare response
        response = {
            'message': 'Wallet created successfully',
            'wallet_id': wallet_ref.id,
            'wallet_addresses': wallet_data['wallet_addresses'],
            'funding_results': funding_results,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Add warnings if any funding failed
        if any(not result.get('funded', False) for result in funding_results.values()):
            response['warnings'] = [
                f"{currency.upper()} funding: {result.get('message', 'Unknown error')}"
                for currency, result in funding_results.items()
                if not result.get('funded', False)
            ]
            response['message'] = 'Wallet created with some funding issues. Check the funding_results field.'

        return jsonify(response), 201

    except Exception as e:
        print(f"Error in create_wallet: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': 'Failed to create wallet',
            'details': str(e)
        }), 500

@app.route('/api/wallet/fund-account', methods=['POST'])
def fund_account():
    """
    Fund a Stellar testnet account using the friendbot.
    
    Expected JSON payload:
    {
        "public_key": "G...",  # The public key to fund
        "email": "user@example.com"  # Optional: User's email for logging
    }
    """
    start_time = datetime.utcnow()
    
    try:
        data = request.get_json() or {}
        public_key = data.get('public_key', '').strip()
        email = data.get('email', '').strip()
        
        # Validate public key
        if not public_key:
            return jsonify({
                'success': False,
                'error': 'Public key is required',
                'code': 'MISSING_PUBLIC_KEY',
                'timestamp': datetime.utcnow().isoformat()
            }), 400
            
        if not is_valid_stellar_address(public_key):
            return jsonify({
                'success': False,
                'error': 'Invalid Stellar public key format. Must start with "G" and be 56 characters long.',
                'code': 'INVALID_PUBLIC_KEY',
                'public_key': public_key,
                'timestamp': datetime.utcnow().isoformat()
            }), 400

        # Log the funding attempt
        print(f"Funding attempt for {'user ' + email + ' ' if email else ''}public key: {public_key}")

        # First check if account exists and is already funded
        account = get_account_safe(public_key)
        
        if account:
            if 'balances' in account and account['balances']:
                balance = float(account['balances'][0]['balance'])
                if balance > 0:
                    print(f"Account {public_key} is already funded with {balance} XLM")
                    return jsonify({
                        'success': True,
                        'message': 'Account is already funded',
                        'public_key': public_key,
                        'balance': balance,
                        'already_funded': True,
                        'network': app.config['STELLAR_NETWORK'],
                        'timestamp': datetime.utcnow().isoformat(),
                        'processing_time_seconds': (datetime.utcnow() - start_time).total_seconds()
                    })
            
            print(f"Account {public_key} exists but has no balance")
        else:
            print(f"Account {public_key} does not exist yet, will attempt to create and fund")

        # Try to fund the account with retries
        max_attempts = 3
        funding_success = False
        last_error = None
        
        for attempt in range(1, max_attempts + 1):
            try:
                print(f"Funding attempt {attempt}/{max_attempts} for {public_key}")
                funding_success = fund_stellar_account(public_key)
                if funding_success:
                    break
            except Exception as e:
                last_error = str(e)
                print(f"Attempt {attempt} failed: {last_error}")
                time.sleep(1)  # Wait a bit before retrying
        
        # Verify the funding was successful
        if funding_success:
            # Give the network a moment to update
            time.sleep(1)
            
            # Verify the funding
            account = get_account_safe(public_key)
            if account and 'balances' in account and account['balances']:
                balance = float(account['balances'][0]['balance'])
                if balance > 0:
                    print(f"Successfully funded account {public_key} with {balance} XLM")
                    return jsonify({
                        'success': True,
                        'message': 'Account funded successfully',
                        'public_key': public_key,
                        'balance': balance,
                        'funded': True,
                        'network': app.config['STELLAR_NETWORK'],
                        'timestamp': datetime.utcnow().isoformat(),
                        'processing_time_seconds': (datetime.utcnow() - start_time).total_seconds()
                    })
        
        # If we get here, funding failed
        error_message = 'Failed to fund account after multiple attempts'
        if last_error:
            error_message += f": {last_error}"
            
        print(f"{error_message} for {public_key}")
        
        return jsonify({
            'success': False,
            'error': error_message,
            'code': 'FUNDING_FAILED',
            'public_key': public_key,
            'network': app.config['STELLAR_NETWORK'],
            'suggestions': [
                'The Stellar testnet friendbot might be experiencing high load',
                'Try again in a few minutes',
                'Check the public key is correct',
                'You can manually fund the account at: https://laboratory.stellar.org/#account-creator',
                'Or use the Stellar Laboratory to create and fund the account'
            ],
            'timestamp': datetime.utcnow().isoformat(),
            'processing_time_seconds': (datetime.utcnow() - start_time).total_seconds()
        }), 500

    except Exception as e:
        error_msg = f"Error in fund_account: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        
        error_code = 'INTERNAL_ERROR'
        status_code = 500
        
        if hasattr(e, 'status'):
            error_code = 'STELLAR_ERROR'
            status_code = e.status
            
        return jsonify({
            'success': False,
            'error': str(e),
            'code': error_code,
            'message': 'An error occurred while funding the account',
            'public_key': public_key if 'public_key' in locals() else None,
            'network': app.config['STELLAR_NETWORK'],
            'timestamp': datetime.utcnow().isoformat(),
            'processing_time_seconds': (datetime.utcnow() - start_time).total_seconds()
        }), status_code

@app.route('/api/wallet/access', methods=['POST'])
def access_wallet():
    """
    Access wallet information including funding status for all currencies
    
    Expected JSON payload:
    {
        "email": "user@example.com",
        "password": "user_password"
    }
    """
    try:
        data = request.get_json() or {}
        email = data.get('email', '').strip()
        password = data.get('password', '')

        if not email or not password:
            return jsonify({
                'success': False,
                'error': 'Email and password are required',
                'code': 'MISSING_CREDENTIALS'
            }), 400

        # Query Firestore for the user's wallet
        try:
            wallets = db.collection('wallets').where('email', '==', email).limit(1).stream()
            user_data = next((wallet.to_dict() for wallet in wallets), None)
        except Exception as e:
            print(f"Firestore error: {str(e)}")
            return jsonify({
                'success': False,
                'error': 'Database error',
                'code': 'DATABASE_ERROR'
            }), 500

        if not user_data:
            return jsonify({
                'success': False,
                'error': 'Wallet not found',
                'code': 'WALLET_NOT_FOUND'
            }), 404

        # Verify password (in a real app, use proper password hashing)
        if user_data.get('password') != password:
            return jsonify({
                'success': False,
                'error': 'Invalid credentials',
                'code': 'INVALID_CREDENTIALS'
            }), 401

        # Get wallet addresses and their funding status
        wallet_addresses = user_data.get('wallet_addresses', {})
        wallet_status = {}
        
        for currency, address in wallet_addresses.items():
            if currency == 'inr':
                # INR is always considered funded with the current balance
                wallet_status[currency] = {
                    'funded': True,
                    'balance': user_data.get('inr_balance', 0),
                    'currency': 'INR',
                    'network': 'fiat'
                }
            else:
                # For crypto wallets, check the actual status
                try:
                    account = get_account_safe(address)
                    if account and 'balances' in account and account['balances']:
                        balance = float(account['balances'][0]['balance'])
                        wallet_status[currency] = {
                            'funded': balance > 0,
                            'balance': balance,
                            'currency': currency.upper(),
                            'network': app.config['STELLAR_NETWORK'],
                            'public_key': address,
                            'needs_funding': balance <= 0,
                            'actions': [
                                'Use /api/wallet/fund-account to fund this wallet'
                            ] if balance <= 0 else None
                        }
                    else:
                        wallet_status[currency] = {
                            'funded': False,
                            'balance': 0,
                            'currency': currency.upper(),
                            'network': app.config['STELLAR_NETWORK'],
                            'public_key': address,
                            'needs_funding': True,
                            'actions': [
                                'Use /api/wallet/fund-account to fund this wallet',
                                'Or visit https://laboratory.stellar.org/#account-creator to fund it manually'
                            ]
                        }
                except Exception as e:
                    print(f"Error checking {currency} wallet {address}: {str(e)}")
                    wallet_status[currency] = {
                        'funded': False,
                        'balance': 0,
                        'currency': currency.upper(),
                        'network': app.config['STELLAR_NETWORK'],
                        'public_key': address,
                        'error': str(e),
                        'needs_funding': True,
                        'actions': [
                            'Unable to check wallet status',
                            'Try again later or contact support'
                        ]
                    }

        # Prepare response
        response = {
            'success': True,
            'message': 'Wallet accessed successfully',
            'wallet_addresses': wallet_addresses,
            'wallet_status': wallet_status,
            'user': {
                'name': user_data.get('name'),
                'email': user_data.get('email'),
                'created_at': user_data.get('created_at', '')
            },
            'network': app.config['STELLAR_NETWORK'],
            'timestamp': datetime.utcnow().isoformat()
        }

        # Add warnings if any wallets need funding
        unfunded_wallets = [
            currency for currency, status in wallet_status.items() 
            if status.get('needs_funding', False)
        ]
        
        if unfunded_wallets:
            response['warnings'] = [
                f"{currency.upper()} wallet needs funding" 
                for currency in unfunded_wallets
            ]

        return jsonify(response)

    except Exception as e:
        print(f"Error in access_wallet: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'success': False,
            'error': 'Failed to access wallet',
            'code': 'INTERNAL_ERROR',
            'details': str(e)
        }), 500

@app.route('/api/wallet/check-account', methods=['POST'])
def check_account():
    """
    Check the status of a Stellar account
    
    Expected JSON payload:
    {
        "public_key": "G..."  # The public key to check
    }
    """
    try:
        data = request.get_json() or {}
        public_key = data.get('public_key', '').strip()
        
        # Validate public key
        if not public_key:
            return jsonify({
                'success': False,
                'error': 'Public key is required',
                'code': 'MISSING_PUBLIC_KEY'
            }), 400
            
        if not is_valid_stellar_address(public_key):
            return jsonify({
                'success': False,
                'error': 'Invalid Stellar public key format',
                'code': 'INVALID_PUBLIC_KEY',
                'public_key': public_key
            }), 400

        # Check if account exists and is funded
        account = get_account_safe(public_key)
        
        if not account:
            return jsonify({
                'success': True,
                'exists': False,
                'funded': False,
                'public_key': public_key,
                'network': app.config['STELLAR_NETWORK'],
                'message': 'Account does not exist on the network',
                'actions': [
                    'Use the /api/wallet/fund-account endpoint to create and fund this account',
                    'Or visit https://laboratory.stellar.org/#account-creator to fund it manually'
                ]
            })
            
        if 'balances' not in account or not account['balances']:
            return jsonify({
                'success': True,
                'exists': True,
                'funded': False,
                'public_key': public_key,
                'network': app.config['STELLAR_NETWORK'],
                'message': 'Account exists but has no balance',
                'actions': [
                    'Use the /api/wallet/fund-account endpoint to fund this account',
                    'Or visit https://laboratory.stellar.org/#account-creator to fund it manually'
                ]
            })
            
        balance = float(account['balances'][0]['balance'])
        
        return jsonify({
            'success': True,
            'exists': True,
            'funded': balance > 0,
            'public_key': public_key,
            'network': app.config['STELLAR_NETWORK'],
            'balance': balance,
            'message': 'Account is funded' if balance > 0 else 'Account exists but has zero balance'
        })

    except Exception as e:
        print(f"Error in check_account: {str(e)}")
        import traceback
        traceback.print_exc()
        
        error_code = 'INTERNAL_ERROR'
        status_code = 500
        
        if hasattr(e, 'status'):
            error_code = 'STELLAR_ERROR'
            status_code = e.status
            
        return jsonify({
            'success': False,
            'error': str(e),
            'code': error_code,
            'message': 'Failed to check account status'
        }), status_code

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV', 'development') == 'development'
    print(f"Starting server in {'debug' if debug else 'production'} mode on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)