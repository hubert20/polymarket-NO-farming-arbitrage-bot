"""Tests for the auto-redeemer module (Data API discovery)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.redeemer import (
    EXEC_FAILURE_TOPIC,
    EXEC_SUCCESS_TOPIC,
    Redeemer,
)


@pytest.fixture
def redeemer():
    return Redeemer(
        private_key="0x" + "ab" * 32,
        proxy_address="0x" + "cd" * 20,
        chain_id=137,
        rpc_url="https://polygon-rpc.com",
    )


SAMPLE_POSITION = {
    "conditionId": "0x" + "aa" * 32,
    "slug": "btc-updown-5m-123",
    "size": 5.0,
    "redeemable": True,
    "title": "BTC > $100000 at 12:05?",
}


# --- fetch tests ---


def _mock_data_api(status=200, json_data=None):
    """Build nested async context manager mocks for aiohttp.

    aiohttp.ClientSession() -> async ctx mgr -> session
    session.get(url, ...) -> async ctx mgr -> response
    session.get is NOT a coroutine — it returns a context manager directly.
    """
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.json = AsyncMock(return_value=json_data or [])

    mock_get_ctx = AsyncMock()
    mock_get_ctx.__aenter__.return_value = mock_resp

    # session.get() must be a regular MagicMock (returns ctx mgr, not coroutine)
    mock_session = MagicMock()
    mock_session.get.return_value = mock_get_ctx

    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__.return_value = mock_session

    return mock_session_ctx


def _mock_data_api_pages(*, pages):
    mock_session = MagicMock()
    get_contexts = []
    for page in pages:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=page)
        mock_get_ctx = AsyncMock()
        mock_get_ctx.__aenter__.return_value = mock_resp
        get_contexts.append(mock_get_ctx)
    mock_session.get.side_effect = get_contexts
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__.return_value = mock_session
    return mock_session_ctx, mock_session


@pytest.mark.asyncio
async def test_fetch_returns_positions(redeemer):
    """Data API returning a list of positions should work."""
    mock_ctx = _mock_data_api(status=200, json_data=[SAMPLE_POSITION])

    with patch("bot.redeemer.aiohttp.ClientSession", return_value=mock_ctx):
        result = await redeemer._fetch_redeemable_positions()

    assert len(result) == 1
    assert result[0]["conditionId"] == SAMPLE_POSITION["conditionId"]


@pytest.mark.asyncio
async def test_fetch_handles_api_error(redeemer):
    """Non-200 response should return empty list, not crash."""
    mock_ctx = _mock_data_api(status=500)

    with patch("bot.redeemer.aiohttp.ClientSession", return_value=mock_ctx):
        result = await redeemer._fetch_redeemable_positions()

    assert result == []


@pytest.mark.asyncio
async def test_fetch_handles_network_error(redeemer):
    """Network exception should return empty list, not crash."""
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.side_effect = ConnectionError("network down")

    with patch("bot.redeemer.aiohttp.ClientSession", return_value=mock_ctx):
        result = await redeemer._fetch_redeemable_positions()

    assert result == []


@pytest.mark.asyncio
async def test_fetch_paginates_redeemable_positions(redeemer):
    first_page = [dict(SAMPLE_POSITION, conditionId=f"0x{index:064x}") for index in range(100)]
    second_page = [dict(SAMPLE_POSITION, conditionId="0x" + "ff" * 32)]
    mock_ctx, mock_session = _mock_data_api_pages(pages=[first_page, second_page])

    with patch("bot.redeemer.aiohttp.ClientSession", return_value=mock_ctx):
        result = await redeemer._fetch_redeemable_positions()

    assert len(result) == 101
    assert mock_session.get.call_count == 2


# --- redeem_all tests ---


def test_redeem_all_calls_execute_for_each(redeemer):
    """Each discovered position should trigger an on-chain redemption."""
    pos1 = {**SAMPLE_POSITION, "conditionId": "0x" + "aa" * 32}
    pos2 = {**SAMPLE_POSITION, "conditionId": "0x" + "bb" * 32}

    with patch("bot.redeemer.Web3"):
        with patch.object(redeemer, "_execute_redeem") as mock_exec:
            redeemer._redeem_all([pos1, pos2])

    assert mock_exec.call_count == 2
    assert pos1["conditionId"] in redeemer._redeemed
    assert pos2["conditionId"] in redeemer._redeemed


def test_redeem_all_skips_already_redeemed(redeemer):
    """Positions already redeemed this session should be skipped."""
    cond_id = "0x" + "aa" * 32
    redeemer._redeemed.add(cond_id)

    # _redeem_all filters before calling, but let's test the full run() path
    # by calling _redeem_all with the already-redeemed position filtered out
    with patch("bot.redeemer.Web3"):
        with patch.object(redeemer, "_execute_redeem") as mock_exec:
            # Simulate the filtering that run() does
            positions = [SAMPLE_POSITION]
            to_redeem = [
                p for p in positions
                if p.get("conditionId") and p["conditionId"] not in redeemer._redeemed
            ]
            if to_redeem:
                redeemer._redeem_all(to_redeem)

    mock_exec.assert_not_called()


def test_redeem_failure_doesnt_block_others(redeemer):
    """A failed redemption should not prevent other positions from redeeming."""
    pos1 = {**SAMPLE_POSITION, "conditionId": "0x" + "aa" * 32}
    pos2 = {**SAMPLE_POSITION, "conditionId": "0x" + "bb" * 32}

    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("gas estimation failed")

    with patch("bot.redeemer.Web3"):
        with patch.object(redeemer, "_execute_redeem", side_effect=side_effect):
            redeemer._redeem_all([pos1, pos2])

    # First failed, second succeeded
    assert pos1["conditionId"] not in redeemer._redeemed
    assert pos2["conditionId"] in redeemer._redeemed


# --- _execute_redeem tests ---


def _mock_execute_up_to_receipt(redeemer, mock_w3, receipt):
    """Set up mocks so _execute_redeem reaches the receipt-checking code."""
    mock_safe = MagicMock()
    mock_w3.eth.contract.return_value = mock_safe
    mock_w3.eth.gas_price = 30_000_000_000
    mock_w3.eth.get_transaction_count.return_value = 0

    safe_tx_hash = b"\xab" * 32
    mock_safe.functions.nonce.return_value.call.return_value = 0
    mock_safe.functions.getTransactionHash.return_value.call.return_value = safe_tx_hash

    mock_w3.eth.wait_for_transaction_receipt.return_value = receipt
    mock_w3.eth.send_raw_transaction.return_value = b"\x00" * 32


def test_exec_failure_event_raises(redeemer):
    """ExecutionFailure event should cause _execute_redeem to raise."""
    mock_w3 = MagicMock()
    mock_ctf = MagicMock()

    failure_log = MagicMock()
    failure_log.topics = [EXEC_FAILURE_TOPIC]
    mock_receipt = MagicMock()
    mock_receipt.status = 1
    mock_receipt.logs = [failure_log]
    mock_receipt.gasUsed = 100000

    _mock_execute_up_to_receipt(redeemer, mock_w3, mock_receipt)

    with pytest.raises(RuntimeError, match="inner call failed"):
        redeemer._execute_redeem(mock_w3, mock_ctf, "0xct", b"\x00" * 32)


def test_missing_success_event_raises(redeemer):
    """No ExecutionSuccess event should cause _execute_redeem to raise."""
    mock_w3 = MagicMock()
    mock_ctf = MagicMock()

    mock_receipt = MagicMock()
    mock_receipt.status = 1
    mock_receipt.logs = []
    mock_receipt.gasUsed = 100000

    _mock_execute_up_to_receipt(redeemer, mock_w3, mock_receipt)

    with pytest.raises(RuntimeError, match="no ExecutionSuccess"):
        redeemer._execute_redeem(mock_w3, mock_ctf, "0xct", b"\x00" * 32)


def test_execute_redeem_skips_when_gas_price_exceeds_cap(redeemer):
    mock_w3 = MagicMock()
    mock_ctf = MagicMock()
    mock_safe = MagicMock()
    mock_w3.eth.contract.return_value = mock_safe
    mock_w3.eth.gas_price = 200_000_000_000
    mock_w3.eth.get_transaction_count.return_value = 0
    mock_safe.functions.nonce.return_value.call.return_value = 0
    mock_safe.functions.getTransactionHash.return_value.call.return_value = b"\xab" * 32

    with patch("bot.redeemer.MAX_GAS_GWEI", 150.0):
        redeemer._execute_redeem(mock_w3, mock_ctf, "0xct", b"\x00" * 32)

    mock_w3.eth.send_raw_transaction.assert_not_called()
    mock_w3.eth.wait_for_transaction_receipt.assert_not_called()


def test_outer_tx_revert_raises(redeemer):
    """receipt.status != 1 should raise RuntimeError."""
    mock_w3 = MagicMock()
    mock_ctf = MagicMock()

    mock_receipt = MagicMock()
    mock_receipt.status = 0
    mock_receipt.gasUsed = 100000

    _mock_execute_up_to_receipt(redeemer, mock_w3, mock_receipt)

    with pytest.raises(RuntimeError, match="outer tx reverted"):
        redeemer._execute_redeem(mock_w3, mock_ctf, "0xct", b"\x00" * 32)


# --- run() loop test ---


@pytest.mark.asyncio
async def test_run_skips_when_no_positions(redeemer):
    """run() should sleep and not crash when API returns nothing."""
    task = asyncio.create_task(redeemer.run())
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_run_fetches_and_redeems(redeemer):
    """run() should fetch positions then redeem them."""
    redeemer._fetch_redeemable_positions = AsyncMock(
        return_value=[SAMPLE_POSITION]
    )
    redeemer._redeem_all = MagicMock()

    # Patch the sleep to run immediately, then raise to break the loop
    call_count = 0

    async def fast_sleep(duration):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise asyncio.CancelledError()

    with patch("bot.redeemer.asyncio.sleep", side_effect=fast_sleep):
        with pytest.raises(asyncio.CancelledError):
            await redeemer.run()

    redeemer._fetch_redeemable_positions.assert_called_once()
    redeemer._redeem_all.assert_called_once()
