from web3 import Web3
from web3.contract import Contract

from app.config import settings
from app.tokens import Token

TRANSFER_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    }
]


def build_transfer_contract(w3: Web3, token: Token) -> Contract:
    return w3.eth.contract(
        address=w3.to_checksum_address(token.address),
        abi=TRANSFER_ABI,
    )


def get_block_hash(w3: Web3, block_number: int) -> str:
    return w3.eth.get_block(block_number)["hash"].to_0x_hex()


def get_safe_block_head(w3: Web3) -> int:
    return w3.eth.get_block_number() - settings.confirmation_blocks
