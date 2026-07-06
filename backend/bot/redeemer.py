"""Periodic redemption of resolved conditional token positions.

Discovers redeemable positions by querying the Polymarket Data API,
then calls redeemPositions() on-chain via Gnosis Safe to convert
winning tokens back to USDC.

No explicit registration needed — the Data API knows what the wallet
holds regardless of how the position was acquired (normal trade,
partial fill, orphaned order, etc.).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

import aiohttp
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

from bot.proxy_wallet import CT_ADDRESS, SAFE_ABI, ZERO_ADDRESS
from bot.trade_ledger import record_order

logger = logging.getLogger(__name__)

# Polymarket Data API (unauthenticated)
DATA_API_BASE = "https://data-api.polymarket.com"
POSITIONS_ENDPOINT = f"{DATA_API_BASE}/positions"

# Polymarket collateral: USDC.e on Polygon
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"

# Binary market index sets: outcome 0 -> bit 1, outcome 1 -> bit 2
BINARY_INDEX_SETS = [1, 2]

# bytes32(0) — top-level conditions (no parent collection)
PARENT_COLLECTION_ID = b"\x00" * 32

DEFAULT_REDEEM_CHECK_INTERVAL_SEC = max(
    30,
    int(os.getenv("PM_REDEEM_CHECK_INTERVAL_SEC", "30")),
)
FETCH_TIMEOUT_SEC = 30
POSITIONS_PAGE_LIMIT = 100
MAX_GAS_GWEI = max(1.0, float(os.getenv("PM_REDEEMER_MAX_GAS_GWEI", "150")))
MAX_RETRIES = 3  # retries before cooldown (not permanent blacklist)
RETRY_COOLDOWN_SEC = 600  # 10 min cooldown after MAX_RETRIES failures
RETRY_DELAY_SEC = 5.0
POST_REDEEM_DELAY_SEC = 4.0  # wait for nonce to settle between redemptions

# Safe event topic hashes (keccak256 of event signatures)
# ExecutionSuccess(bytes32,uint256)
EXEC_SUCCESS_TOPIC = bytes.fromhex(
    "442e715f626346e8c54381002da614f62bee8d27386535b2521ec8540898556e"
)
# ExecutionFailure(bytes32,uint256)
EXEC_FAILURE_TOPIC = bytes.fromhex(
    "23428b18acfb3ea64b08dc0c1d296ea9c09702c09083ca5272e64d115b687d23"
)

# Minimum ABI for CTF redemption
CTF_REDEEM_ABI = [
    {
        "inputs": [
            {"name": "collateralToken", "type": "address"},
            {"name": "parentCollectionId", "type": "bytes32"},
            {"name": "conditionId", "type": "bytes32"},
            {"name": "indexSets", "type": "uint256[]"},
        ],
        "name": "redeemPositions",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


class Redeemer:
    """Discovers and redeems resolved positions via Polymarket Data API."""

    def __init__(
        self,
        private_key: str,
        proxy_address: str,
        chain_id: int,
        rpc_url: str,
        session: aiohttp.ClientSession | None = None,
        check_interval_sec: int = DEFAULT_REDEEM_CHECK_INTERVAL_SEC,
    ):
        self._private_key = private_key
        self._proxy_address = proxy_address
        self._chain_id = chain_id
        self._rpc_url = rpc_url
        self._redeemed: set[str] = set()
        self._failed_attempts: dict[str, int] = {}  # conditionId -> consecutive failures
        self._failed_at: dict[str, float] = {}  # conditionId -> timestamp of last failure
        self._nonce_gap_first_seen: float = 0.0  # when we first saw pending > confirmed
        self._session = session
        self._check_interval_sec = max(30, int(check_interval_sec))

    async def run(self) -> None:
        """Async loop: discover and redeem positions every 2 minutes."""
        logger.info("Redeemer started, checking every %ds", self._check_interval_sec)
        while True:
            await asyncio.sleep(self._check_interval_sec)
            try:
                positions = await self._fetch_redeemable_positions()
                if not positions:
                    continue
                now = time.time()
                # Reset failed attempts after cooldown — never permanently blacklist
                for cid in list(self._failed_attempts):
                    if (
                        self._failed_attempts[cid] >= MAX_RETRIES
                        and (now - self._failed_at.get(cid, 0)) >= RETRY_COOLDOWN_SEC
                    ):
                        logger.info("redeemer_cooldown_reset: %s", cid[:20])
                        self._failed_attempts.pop(cid)
                        self._failed_at.pop(cid, None)

                to_redeem = [
                    p for p in positions
                    if p.get("conditionId")
                    and p["conditionId"] not in self._redeemed
                    and self._failed_attempts.get(p["conditionId"], 0) < MAX_RETRIES
                ]
                if to_redeem:
                    logger.info(
                        "redeemer_batch",
                        extra={
                            "total_redeemable": len(positions),
                            "to_redeem": len(to_redeem),
                            "already_redeemed": len(self._redeemed),
                            "max_retried_out": sum(
                                1 for p in positions
                                if self._failed_attempts.get(p.get("conditionId", ""), 0) >= MAX_RETRIES
                            ),
                        },
                    )
                    await asyncio.to_thread(self._redeem_all, to_redeem)
            except Exception as e:
                logger.error("redeemer_error: %s", e)

    async def _fetch_redeemable_positions(self) -> list[dict]:
        """Query Polymarket Data API for redeemable positions held by this wallet."""
        try:
            positions: list[dict] = []
            offset = 0
            if self._session is not None:
                session = self._session
                while True:
                    page = await self._do_fetch(session, offset=offset)
                    positions.extend(page)
                    if len(page) < POSITIONS_PAGE_LIMIT:
                        return positions
                    offset += len(page)
            async with aiohttp.ClientSession() as session:
                while True:
                    page = await self._do_fetch(session, offset=offset)
                    positions.extend(page)
                    if len(page) < POSITIONS_PAGE_LIMIT:
                        return positions
                    offset += len(page)
        except Exception as e:
            logger.warning("redeemer_fetch_failed: %s", e)
            return []

    async def _do_fetch(self, session: aiohttp.ClientSession, *, offset: int) -> list[dict]:
        params = {
            "user": self._proxy_address,
            "redeemable": "true",
            "sizeThreshold": "0",
            "limit": str(POSITIONS_PAGE_LIMIT),
            "offset": str(offset),
        }
        async with session.get(
            POSITIONS_ENDPOINT,
            params=params,
            timeout=aiohttp.ClientTimeout(total=FETCH_TIMEOUT_SEC),
        ) as resp:
            if resp.status != 200:
                logger.warning(
                    "redeemer_api_error: status=%d", resp.status,
                )
                return []
            data = await resp.json()
            if isinstance(data, dict):
                data = data.get("data") or data.get("positions") or []
            if not isinstance(data, list):
                logger.warning(
                    "redeemer_api_unexpected: type=%s",
                    type(data).__name__,
                )
                return []
            return [item for item in data if isinstance(item, dict)]

    def _clear_stuck_nonces(self, w3: Web3) -> bool:
        """Detect and cancel stuck transactions by sending zero-value replacements.

        Only acts when a nonce gap has persisted for > 180s (matching the
        redeem tx timeout). A brief gap from a normal in-flight tx is ignored.
        Respects the same MAX_GAS_GWEI cap used for real redeems.

        Returns True if it's safe to proceed with redeems, False if nonces
        are still stuck and redeems should be skipped this cycle.
        """
        signer = Account.from_key(self._private_key)
        try:
            confirmed = int(w3.eth.get_transaction_count(signer.address, "latest"))
            pending = int(w3.eth.get_transaction_count(signer.address, "pending"))
        except Exception as e:
            logger.warning("redeemer_nonce_check_failed: %s", e)
            return False  # can't verify nonce is clear — skip this cycle

        stuck = pending - confirmed
        if stuck <= 0:
            self._nonce_gap_first_seen = 0.0
            return True

        now = time.time()
        if self._nonce_gap_first_seen <= 0.0:
            self._nonce_gap_first_seen = now
            logger.info(
                "redeemer_nonce_gap_detected",
                extra={
                    "confirmed_nonce": confirmed,
                    "pending_nonce": pending,
                    "stuck_count": stuck,
                },
            )
            return False  # first sighting — skip redeems, wait to see if it clears

        gap_age_sec = now - self._nonce_gap_first_seen
        if gap_age_sec < 180:
            return False  # not stuck long enough — skip redeems this cycle

        logger.warning(
            "redeemer_clearing_stuck_nonces",
            extra={
                "confirmed_nonce": confirmed,
                "pending_nonce": pending,
                "stuck_count": stuck,
                "gap_age_sec": round(gap_age_sec, 1),
            },
        )

        gas_price_wei = int(w3.eth.gas_price * 2)
        gas_price_gwei = gas_price_wei / 1_000_000_000
        if gas_price_gwei > MAX_GAS_GWEI:
            logger.warning(
                "redeemer_nonce_cancel_gas_too_high",
                extra={"gas_price_gwei": round(gas_price_gwei, 3), "max_gas_gwei": MAX_GAS_GWEI},
            )
            return False

        cleared = 0
        for nonce in range(confirmed, pending):
            try:
                tx = {
                    "from": signer.address,
                    "to": signer.address,
                    "value": 0,
                    "nonce": nonce,
                    "gas": 21000,
                    "gasPrice": gas_price_wei,
                    "chainId": self._chain_id,
                }
                signed = w3.eth.account.sign_transaction(tx, self._private_key)
                w3.eth.send_raw_transaction(signed.raw_transaction)
                cleared += 1
            except Exception as e:
                logger.warning("redeemer_nonce_cancel_failed: nonce=%d %s", nonce, e)
                break

        if cleared > 0:
            try:
                latest_confirmed = confirmed
                for _ in range(60):
                    time.sleep(1)
                    latest_confirmed = int(w3.eth.get_transaction_count(signer.address, "latest"))
                    if latest_confirmed >= pending:
                        break
                if latest_confirmed >= pending:
                    self._nonce_gap_first_seen = 0.0
                    logger.info(
                        "redeemer_nonces_cleared",
                        extra={
                            "cleared": cleared,
                            "new_confirmed_nonce": latest_confirmed,
                        },
                    )
                    return True
                else:
                    logger.warning(
                        "redeemer_nonce_clear_incomplete",
                        extra={
                            "cleared_sent": cleared,
                            "confirmed_nonce": latest_confirmed,
                            "target_nonce": pending,
                        },
                    )
                    return False
            except Exception as e:
                logger.warning("redeemer_nonce_wait_failed: %s", e)
                return False
        return False

    def _redeem_all(self, positions: list[dict]) -> None:
        """Redeem all discovered positions on-chain, one at a time with nonce settling."""
        w3 = Web3(Web3.HTTPProvider(self._rpc_url, request_kwargs={"timeout": 30}))
        try:
            w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        except ValueError:
            pass

        # Clear any stuck nonces before attempting redeems
        if not self._clear_stuck_nonces(w3):
            return  # nonces still stuck — skip redeems this cycle

        ct_address = Web3.to_checksum_address(CT_ADDRESS)
        ctf = w3.eth.contract(address=ct_address, abi=CTF_REDEEM_ABI)

        for i, pos in enumerate(positions):
            condition_id = pos["conditionId"]
            slug = pos.get("slug") or pos.get("title") or condition_id[:20]
            size = pos.get("size", 0)

            try:
                cid_hex = condition_id
                if cid_hex.startswith("0x"):
                    cid_hex = cid_hex[2:]
                condition_bytes = bytes.fromhex(cid_hex)

                logger.info(
                    "redeemer_redeeming",
                    extra={
                        "slug": slug,
                        "condition_id": condition_id[:20] + "...",
                        "size": size,
                        "attempt": self._failed_attempts.get(condition_id, 0) + 1,
                        "batch_index": f"{i + 1}/{len(positions)}",
                    },
                )
                self._execute_redeem(w3, ctf, ct_address, condition_bytes)
                self._redeemed.add(condition_id)
                self._failed_attempts.pop(condition_id, None)
                logger.info("redeemer_success: %s", slug)
                try:
                    size_f = float(size) if size else 0.0
                except (ValueError, TypeError):
                    size_f = 0.0
                record_order(
                    action="redeem",
                    market_slug=str(slug),
                    side="",
                    token_id=condition_id,
                    amount=size_f,
                    interval_start=0,
                )

                # Wait for nonce to settle before next redemption
                if i < len(positions) - 1:
                    time.sleep(POST_REDEEM_DELAY_SEC)

            except Exception as e:
                count = self._failed_attempts.get(condition_id, 0) + 1
                self._failed_attempts[condition_id] = count
                self._failed_at[condition_id] = time.time()
                logger.warning(
                    "redeemer_failed",
                    extra={
                        "slug": slug,
                        "error": str(e),
                        "attempt": count,
                        "max_retries": MAX_RETRIES,
                        "will_retry": count < MAX_RETRIES,
                    },
                )
                record_order(
                    action="redeem_failed",
                    market_slug=str(slug),
                    side="",
                    token_id=condition_id,
                    amount=0,
                    interval_start=0,
                    error=f"attempt={count}: {e}",
                )
                # On nonce/signature errors, wait longer before trying the next one
                if "GS026" in str(e) or "nonce" in str(e).lower():
                    time.sleep(POST_REDEEM_DELAY_SEC * 2)
                else:
                    time.sleep(RETRY_DELAY_SEC)

    def _execute_redeem(
        self,
        w3: Web3,
        ctf,
        ct_address: str,
        condition_id: bytes,
    ) -> None:
        """Execute redeemPositions via Gnosis Safe."""
        signer = Account.from_key(self._private_key)
        proxy = Web3.to_checksum_address(self._proxy_address)
        safe = w3.eth.contract(address=proxy, abi=SAFE_ABI)
        usdc = Web3.to_checksum_address(USDC_ADDRESS)

        call_data = ctf.functions.redeemPositions(
            usdc,
            PARENT_COLLECTION_ID,
            condition_id,
            BINARY_INDEX_SETS,
        )._encode_transaction_data()

        # Read nonce fresh — critical for sequential redemptions
        safe_nonce = int(safe.functions.nonce().call())
        safe_tx_hash = safe.functions.getTransactionHash(
            ct_address,
            0,
            call_data,
            0,
            0,
            0,
            0,
            ZERO_ADDRESS,
            ZERO_ADDRESS,
            safe_nonce,
        ).call()

        signed_message = Account.sign_message(
            encode_defunct(hexstr=Web3.to_hex(safe_tx_hash)),
            private_key=self._private_key,
        )
        safe_signature = (
            signed_message.r.to_bytes(32, "big")
            + signed_message.s.to_bytes(32, "big")
            + bytes([signed_message.v + 4])
        )

        exec_tx = safe.functions.execTransaction(
            ct_address,
            0,
            call_data,
            0,
            0,
            0,
            0,
            ZERO_ADDRESS,
            ZERO_ADDRESS,
            safe_signature,
        )

        tx_params = {
            "from": signer.address,
            "nonce": w3.eth.get_transaction_count(signer.address, "pending"),
            "chainId": self._chain_id,
        }
        gas_price_wei = int(w3.eth.gas_price)
        gas_price_gwei = gas_price_wei / 1_000_000_000
        if gas_price_gwei > MAX_GAS_GWEI:
            logger.warning(
                "redeemer_gas_too_high",
                extra={
                    "gas_price_gwei": round(gas_price_gwei, 3),
                    "max_gas_gwei": MAX_GAS_GWEI,
                },
            )
            return
        tx_params["gasPrice"] = gas_price_wei
        try:
            tx_params["gas"] = (
                int(exec_tx.estimate_gas({"from": signer.address}) * 1.2) + 50_000
            )
        except Exception as gas_err:
            raise RuntimeError(
                f"Gas estimation failed — aborting to avoid burning gas on likely-doomed tx: {gas_err}"
            ) from gas_err

        signed_tx = w3.eth.account.sign_transaction(
            exec_tx.build_transaction(tx_params), self._private_key
        )
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)

        if receipt.status != 1:
            raise RuntimeError(
                f"Redemption outer tx reverted: {Web3.to_hex(tx_hash)}"
            )

        # Safe's execTransaction wraps the inner call — receipt.status==1 only
        # means the Safe tx mined, NOT that redeemPositions succeeded.
        # Check for ExecutionFailure / ExecutionSuccess events.
        for log_entry in receipt.logs:
            if not log_entry.topics:
                continue
            topic = bytes(log_entry.topics[0])
            if topic == EXEC_FAILURE_TOPIC:
                raise RuntimeError(
                    f"Safe inner call failed (ExecutionFailure): "
                    f"{Web3.to_hex(tx_hash)}"
                )

        # Verify ExecutionSuccess was emitted
        found_success = any(
            log_entry.topics
            and bytes(log_entry.topics[0]) == EXEC_SUCCESS_TOPIC
            for log_entry in receipt.logs
        )
        if not found_success:
            raise RuntimeError(
                f"Safe tx mined but no ExecutionSuccess event: "
                f"{Web3.to_hex(tx_hash)}"
            )

        logger.info(
            "redeemer_tx_confirmed",
            extra={
                "tx_hash": Web3.to_hex(tx_hash),
                "gas_used": receipt.gasUsed,
            },
        )
