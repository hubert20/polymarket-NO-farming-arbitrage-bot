from unittest.mock import patch

import pytest

from bot.config import ExchangeConfig
from bot.exchange.paper import PaperExchangeClient
from bot.main import _build_exchange, _resolve_live_wallet_address, _validate_live_runtime


def test_validate_live_runtime_requires_database_url():
    exchange = ExchangeConfig(
        host="https://clob.polymarket.com",
        chain_id=137,
        signature_type=2,
        private_key="0xabc",
        funder_address="0xfunder",
        live_send_enabled=True,
    )
    with pytest.raises(ValueError, match="DATABASE_URL"):
        _validate_live_runtime(exchange, None)


def test_build_exchange_uses_paper_client_when_live_send_disabled():
    exchange = ExchangeConfig(
        host="https://clob.polymarket.com",
        chain_id=137,
        signature_type=2,
        private_key=None,
        funder_address=None,
        live_send_enabled=False,
    )
    built = _build_exchange(exchange)
    assert isinstance(built, PaperExchangeClient)


def test_build_exchange_uses_live_client_when_enabled():
    exchange = ExchangeConfig(
        host="https://clob.polymarket.com",
        chain_id=137,
        signature_type=0,
        private_key="0xabc",
        funder_address=None,
        live_send_enabled=True,
    )
    sentinel = object()
    with patch("bot.exchange.polymarket_clob.PolymarketClobExchangeClient", return_value=sentinel) as factory:
        built = _build_exchange(exchange)
    assert built is sentinel
    factory.assert_called_once_with(exchange, allow_trading=True)


def test_resolve_live_wallet_address_uses_signer_for_direct_eoa():
    exchange = ExchangeConfig(
        host="https://clob.polymarket.com",
        chain_id=137,
        signature_type=0,
        private_key="0xabc",
        funder_address=None,
        live_send_enabled=True,
    )
    signer = type("Signer", (), {"address": "0xsigner"})()
    with patch("eth_account.Account.from_key", return_value=signer) as from_key:
        wallet_address = _resolve_live_wallet_address(exchange)
    assert wallet_address == "0xsigner"
    from_key.assert_called_once_with("0xabc")
