import requests
import random
import time
import re
import sys
from fake_useragent import UserAgent
from twocaptcha import TwoCaptcha, ApiException, ValidationException, NetworkException, TimeoutException
from typing import List, Optional
from loguru import logger
from dotenv import load_dotenv
import os

load_dotenv()
logger.remove(0)
logger.add(sys.stderr, level='DEBUG', colorize=True, format="{time:HH:mm:ss} <level>| {level: <7} | {message}</level>")

def load_lines(file_path: str) -> List[str]:
    try:
        with open(file_path, 'r') as file:
            return [line.strip() for line in file if line.strip()]
    except FileNotFoundError:
        logger.warning(f"{file_path} not found, continuing without it")
        return []

def generate_fake_user_agent() -> str:
    return UserAgent().random

def solve_captcha(solver: TwoCaptcha, sitekey: str, url: str, useragent: str, max_attempts: int = 3) -> Optional[str]:
    for attempt in range(max_attempts):
        try:
            logger.info("Solving CAPTCHA...")
            result = solver.hcaptcha(sitekey=sitekey, url=url, useragent=useragent)
            logger.info("CAPTCHA solved")
            return result['code']
        except (ValidationException, NetworkException, TimeoutException, ApiException) as e:
            logger.error(f"Error solving CAPTCHA: {e}")
            if attempt < max_attempts - 1:
                backoff_time = 2 ** (attempt + 1)
                logger.info(f"Retrying in {backoff_time} seconds...")
                time.sleep(backoff_time)
    logger.error("Failed to solve CAPTCHA after maximum attempts")
    return None

def make_api_request(api_url: str, captcha_code: str, address: str, proxy: Optional[str], max_attempts: int = 3) -> Optional[str]:
    headers = generate_headers()
    files = {'address': (None, address), 'coins[]': (None, '5token'), 'h-captcha-response': (None, captcha_code)}
    proxies = {'http': proxy} if proxy else None
    log_message = 'with' if proxy else 'without'
    logger.info(f'Making POST request to API {log_message} proxy...')

    for attempt in range(max_attempts):
        try:
            response = requests.post(api_url, headers=headers, files=files, proxies=proxies)
            return handle_response(response)
        except requests.RequestException as e:
            logger.error(f"Request failed: {e}")
            if attempt < max_attempts - 1:
                backoff_time = 2 ** (attempt + 1)
                logger.info(f"Retrying in {backoff_time} seconds...")
                time.sleep(backoff_time)
    logger.error("Failed to make API request after maximum attempts")
    return None

def generate_headers() -> dict:
    user_agent = generate_fake_user_agent()
    platform_match = re.search(r'\([^;]+', user_agent)
    system_platform = platform_match.group(0)[1:] if platform_match else "Unknown"
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "Access-Control-Allow-Headers": "Origin, X-Requested-With, Content-Type, Accept",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Origin": "*",
        "Dnt": "1",
        "Origin": "https://faucet.testnet.swisstronik.com",
        "Priority": "u=1, i",
        "Referer": "https://faucet.testnet.swisstronik.com/",
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": user_agent,
        "sec-ch-ua-platform": f'"{system_platform}"'
    }

def handle_response(response: requests.Response) -> Optional[str]:
    if response.status_code == 200:
        try:
            data = response.json()
            return data.get('TxHash')
        except ValueError:
            logger.error("Error: Received invalid JSON")
            logger.error(f"Response content: {response.content}")
    elif response.status_code == 429:
        logger.warning("Received 429 Too Many Requests, skipping to next wallet")
        return "too_many_requests"
    else:
        logger.error(f"Error: {response.status_code}, Response content: {response.content}")
    return None

def save_successful_wallet(wallet: str, txhash: str) -> None:
    with open("successful_wallets.txt", "a") as file:
        file.write(f"{wallet}, https://explorer-cosmos.testnet.swisstronik.com/swisstronik/tx/{txhash}\n")

def banner() -> None:
    art = """
 _________________________________________
|      AUTO GET SWISSTRONIK FAUCET        |
|   GITHUB: https://github.com/Tnodes     |
|   TELEGRAM: https://t.me/tdropid        |   
|_________________________________________|     
    """
    print(art)

def main() -> None:
    banner()

    api_key = os.getenv("API_KEY")
    if not api_key:
        logger.error("API key not found in environment variables")
        return
    
    sitekey = '18447955-21a0-4cd7-aed7-8436a4ada636'
    url = 'https://faucet.testnet.swisstronik.com'
    
    api_url = 'https://faucet-backend.testnet.swisstronik.com/'

    proxies = load_lines('proxy.txt')
    wallets = load_lines('wallet.txt')
    
    if not wallets:
        logger.error("No wallets to process.")
        return

    solver = TwoCaptcha(api_key)

    for wallet in wallets:
        logger.info(f"Processing wallet: {wallet}")
        proxy = random.choice(proxies) if proxies else None
        captcha_code = solve_captcha(solver, sitekey, url, generate_fake_user_agent())
        
        if not captcha_code:
            logger.error(f"Unable to solve CAPTCHA after multiple attempts for wallet {wallet}, skipping request")
            continue
        
        txhash = make_api_request(api_url, captcha_code, wallet, proxy)
        if txhash and txhash not in ["too_many_requests"]:
            logger.info(f"Received token: {txhash} for wallet {wallet}")
            save_successful_wallet(wallet, txhash)

        time.sleep(20)

if __name__ == "__main__":
    main()