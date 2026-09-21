import re

# A handful of "ticker" rows in the DB aren't real, look-up-able equity symbols: an unresolved
# CUSIP falls back to "CUSIP:<cusip>" (see whales_service._get_or_create_ticker_by_cusip), a bond
# position's OpenFIGI-resolved "symbol" can be a space-separated descriptor like
# "AEIS 2.5 09/15/28", and a handful of PTR asset descriptions parse to a literal placeholder like
# "NONE", "N/A", or "[NONE]". None of these are something a user could look up or buy, and one of
# them (a bracketed symbol) actively breaks Next.js's <Link href="/stock/[NONE]"> — it reads as
# dynamic-route syntax — so this filter needs to catch shapes, not just a fixed exclude list.
_VALID_SYMBOL_RE = re.compile(r"^[A-Z0-9.\-/]{1,10}$")
_JUNK_SYMBOLS = {"NONE", "N/A", "NULL", ""}


def is_real_symbol(symbol: str) -> bool:
    if symbol.startswith("CUSIP:"):
        return False
    if symbol.upper() in _JUNK_SYMBOLS:
        return False
    return bool(_VALID_SYMBOL_RE.match(symbol))
