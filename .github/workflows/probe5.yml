name: RollerCoin Probe5 (Token Blaster / Crypto Hamster)

on:
  workflow_dispatch:
    inputs:
      games:
        description: "Token Blaster,Crypto Hamster"
        default: "Token Blaster,Crypto Hamster"

concurrency:
  group: rollercoin-session
  cancel-in-progress: false

jobs:
  probe5:
    runs-on: ubuntu-latest
    timeout-minutes: 25
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'
          cache: 'pip'
      - run: pip install -r requirements.txt

      - name: Restore session state
        uses: actions/cache/restore@v4
        with:
          path: session_state
          key: rc-session-${{ github.run_id }}
          restore-keys: rc-session-

      - name: Run probe5
        run: python probe5.py
        env:
          RC_SESSION: ${{ secrets.RC_SESSION }}
          RC_LOCAL: ${{ secrets.RC_LOCAL }}
          GAMES: ${{ github.event.inputs.games || 'Token Blaster,Crypto Hamster' }}
          HEADLESS: "1"

      - name: Save session state
        if: always()
        uses: actions/cache/save@v4
        with:
          path: session_state
          key: rc-session-${{ github.run_id }}

      - name: Upload probe5 output
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: probe5
          path: probe5/
          if-no-files-found: ignore
