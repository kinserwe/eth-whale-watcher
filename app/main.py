import time

from web3 import Web3

from app.chain import build_transfer_contract
from app.config import settings
from app.logging_config import configure_logging
from app.scanner import poll_contract
from app.tokens import USDT

POLL_INTERVAL_SECONDS = 60


def main():
    token = USDT
    w3 = Web3(Web3.HTTPProvider(settings.eth_rpc_url))
    contract = build_transfer_contract(w3, token)

    while True:
        poll_contract(w3, contract, token)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    configure_logging()
    main()
