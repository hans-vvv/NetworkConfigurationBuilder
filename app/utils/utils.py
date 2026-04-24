from __future__ import annotations

import inspect
import ipaddress
import json
from collections.abc import Sized
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional, TypeVar, cast

import pandas as pd

from app.db.session import SessionLocal


@contextmanager
def db_session(dry_run: bool = False):
    """
    Provide a transactional database session scope.

    Creates a new `SessionLocal` instance and yields it to the caller.
    On normal completion, the transaction is committed unless `dry_run`
    is True, in which case the transaction is rolled back. If an exception
    occurs within the context block, the transaction is rolled back and
    the exception is re-raised. The session is always closed.

    Parameters
    ----------
    dry_run : bool, optional
        If True, the transaction is rolled back instead of committed.

    Yields
    ------
    Session
        An active SQLAlchemy session instance.
    """
    session = SessionLocal()
    try:
        yield session

        if dry_run:
            session.rollback()
        else:
            session.commit()

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


T = TypeVar("T")


def require(value: Optional[T], message: str) -> T:
    """
    Ensure that a value is present (not None and not empty).

    Missing means:
      - None
      - "" or whitespace-only strings
      - empty sized containers (len(value) == 0), e.g. [], {}, set(), ()

    Note: falsy scalars like 0 or False are allowed.
    """

    missing = False

    if value is None:
        missing = True
    elif isinstance(value, str):
        missing = (value.strip() == "")
    elif isinstance(value, Sized):
        # catches list/dict/set/tuple/etc.; does NOT catch 0/False
        try:
            missing = (len(value) == 0)
        except TypeError:
            missing = False

    if missing:
        frame = inspect.stack()[1]  # caller of require()
        func_name = frame.function
        cls_name = (
            frame.frame.f_locals["self"].__class__.__name__
            if "self" in frame.frame.f_locals
            else None
        )
        origin = f"{cls_name}.{func_name}" if cls_name else func_name
        raise ValueError(f"[{origin}] {message}")

    return cast(T, value)


def load_sheet(*, sheet_name: str , wb_name: str | Path) -> pd.DataFrame:

        """
        Load and normalize an Excel worksheet into a cleaned pandas DataFrame.

        The function reads a sheet from the configured workbook, coerces all values
        to object dtype, and applies cell-level normalization:
        - Missing values (NaN) are converted to None
        - Strings are stripped of surrounding whitespace; empty strings become None
        - Non-string values are coerced to strings and stripped

        Fully empty rows (all values None) are removed.
        """
        
        df = pd.read_excel(
            wb_name,
            sheet_name=sheet_name,
            dtype=object,
        )

        def _clean_cell(x):
            if pd.isna(x):
                return None
            if isinstance(x, str):
                x = x.strip()
                return x or None
            return str(x).strip()

        df = df.apply(lambda col: col.map(_clean_cell))

        # Drop fully empty rows
        df = df.dropna(how="all")

        return df


def cidr_to_address_mask(cidr: str) -> tuple[str, str]:
    "Jinja2 helper"
    ip = ipaddress.ip_interface(cidr)
    return str(ip.ip), str(ip.network.netmask)


def deep_merge(base: dict, override: dict) -> dict:
    """
    Recursively merge two dictionaries.

    For each key in `override`:
    - If the key exists in both dictionaries and both corresponding values
    are dictionaries, they are merged recursively.
    - Otherwise, the value from `override` replaces the value in `base`.

    The merge is non-destructive: `base` is shallow-copied before merging,
    and a new dictionary is returned.
    """
    result = base.copy()
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Tree(dict[str, Any]):
    """ Autovivificious dictionary """
    def __missing__(self, key: str) -> Tree:
        value = self[key] = type(self)()
        return value

    def __str__(self) -> str:
        return json.dumps(self, indent=4)


def jprint(dict_: dict) -> None:
    """Helper to print user friendly output"""
    print(json.dumps(dict_, indent=4))


def peer_ip_on_p2p(value: str) -> str:
    """
    Given an IPv4 interface string like '10.86.64.19/31' or '192.0.2.1/30',
    return the peer IP address on the point-to-point subnet.

    Supports only /30 and /31.
    """
    iface = ipaddress.IPv4Interface(value)
    ip = iface.ip
    network = iface.network
    prefix = network.prefixlen

    if prefix == 31:
        # Flip last bit (two-address subnet)
        return str(ipaddress.IPv4Address(int(ip) ^ 1))

    if prefix == 30:
        net = int(network.network_address)
        offset = int(ip) - net

        # Valid host offsets in /30 are 1 and 2
        if offset == 1:
            return str(ipaddress.IPv4Address(net + 2))
        if offset == 2:
            return str(ipaddress.IPv4Address(net + 1))

        raise ValueError(f"{value} is not a usable host address in a /30")

    raise ValueError(f"{value} is not /30 or /31")

