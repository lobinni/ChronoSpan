#!/usr/bin/env python3
"""Deploy ChronoSpan to StudioNet and exercise it end to end.

    python -m pip install genlayer-py
    python samples/deploy_and_call.py

Requires a funded StudioNet account.  ``genlayer-py`` exposes the client
surface used below (``create_client`` / ``create_account`` /
``deploy_contract`` / ``write_contract`` / ``read_contract``); if your
installed version differs, run ``python -m pip show genlayer-py`` and adjust
the two helper names - nothing else in the script changes.
"""

import os
import sys
from pathlib import Path

from genlayer_py import create_account, create_client
from genlayer_py.chains import studionet

SOURCE = Path(__file__).resolve().parents[1] / "contracts" / "chrono_span.py"

BEFORE = "2016-12-31T23:59:59Z"
INSERTED = "2016-12-31T23:59:60Z"
MIDNIGHT = "2017-01-01T00:00:00Z"


def main() -> int:
    key = os.environ.get("GENLAYER_PRIVATE_KEY")
    account = create_account(key) if key else create_account()
    client = create_client(chain=studionet, account=account)

    code = SOURCE.read_text(encoding="utf-8")
    print(f"deploying {SOURCE.name} ({len(code)} bytes) as {account.address}")

    deploy_tx = client.deploy_contract(code=code, args=[])
    receipt = client.wait_for_transaction_receipt(deploy_tx)
    address = receipt.contract_address
    print(f"contract: {address}")

    # 1. Consensus call: leader and validators download and verify both
    #    publisher lists, then must return byte-identical canonical JSON.
    print("importing the publisher evidence ...")
    table_id = client.write_contract(
        address=address, functionName="import_schedule", args=[]
    )
    client.wait_for_transaction_receipt(table_id)
    table = client.read_contract(
        address=address, functionName="list_tables", args=[]
    )[0]
    print(f"table id: {table}")

    # 2. Reads are free and instant.
    coverage = client.read_contract(
        address=address, functionName="coverage", args=[table]
    )
    print(f"coverage: {coverage['first_utc']} .. {coverage['last_utc_exclusive']}")

    interval = client.read_contract(
        address=address,
        functionName="measure",
        args=[table, BEFORE, MIDNIGHT],
    )
    print(
        f"measure  {BEFORE} -> {MIDNIGHT} = "
        f"{interval['elapsed_seconds']} SI seconds, "
        f"changes {interval['offset_changes']}"
    )

    print(f"advance +1s -> {client.read_contract(address=address, functionName='advance', args=[table, BEFORE, 1])}")
    print(f"rewind  -2s -> {client.read_contract(address=address, functionName='rewind', args=[table, MIDNIGHT, 2])}")
    print(
        "next transition ->",
        client.read_contract(
            address=address, functionName="next_transition", args=[table, "2016-06-01T00:00:00Z"]
        ),
    )

    # 3. Reverts are reverts: an unknown table id never returns partial data.
    try:
        client.read_contract(address=address, functionName="get_table", args=["0" * 64])
    except Exception as error:  # noqa: BLE001 - the RPC surfaces the revert text
        print(f"unknown table id -> {error}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
