# RAB9 Field Testing

This guide is for testers validating the bot in the allowed Telegram group. Do not paste private keys, seed phrases, exchange API keys, or unreleased contract addresses into chat.

## Before Testing

1. Confirm the bot process is running.
2. Run `/status`.
3. Check that Dexscreener is online.
4. Check whether Grok and Arkham keys are loaded if those features are in scope.
5. Use only the Telegram group configured in `TELEGRAM_GROUP_ID`.

Record for each test:

- command sent;
- timestamp;
- whether the bot replied;
- whether the reply was split cleanly if long;
- any error text;
- candidate token or wallet used.

## Scanner Tests

### `/micro`

Run:

```text
/micro
```

Expected:

- bot first says it is starting Micro scan;
- final response contains `RAB9 Scan Micro`;
- response shows filters, checked pairs, passed count, and rejected/no-data count;
- if candidates exist, each has chain, DEX, MC, liquidity, volume, score, risk, analyze command, watch command, and Dexscreener URL;
- if no candidates pass, empty-result text is acceptable.

### `/degen`

Run:

```text
/degen
```

Expected:

- bot first says it is starting Degen scan;
- final response contains `RAB9 Scan Degen`;
- market-cap filter is the degen range;
- candidate blocks include `/token` and `/watch` follow-up commands.

### `/scan`

Run:

```text
/scan
```

Expected:

- bot first says it is starting Normal scan;
- final response contains `RAB9 Scan Normal`;
- candidates, if any, are sorted toward stronger score/volume/liquidity;
- no crash when Dexscreener returns no suitable pairs.

### `/hot`

Run:

```text
/hot
```

Expected:

- bot first says it is starting Hot Scan;
- final response contains `RAB9 Hot Scan`;
- response shows 1h volume, 1h price change, sell/buy pressure, score, risk, and hot reason;
- no candidates is acceptable when the market has no current impulse.

## Token Intel

Use an address from a scanner result.

Run:

```text
/token solana TOKEN_ADDRESS
```

Expected:

- bot acknowledges analysis may take a few seconds;
- response includes token identity, chain, DEX, price/MC/liquidity/volume metrics, score, risk, and decision layer;
- response does not claim missing data such as holders, audits, smart-money flow, or high/low unless present;
- if Grok/xAI is unavailable, the error should be visible and the bot should stay alive.

Negative test:

```text
/token
```

Expected:

- bot returns usage format instead of crashing.

## Token Watchlist

Use a token address from `/micro`, `/degen`, `/scan`, `/hot`, or `/token`.

Add:

```text
/watch solana TOKEN_ADDRESS field test
```

Expected:

- bot says it added or updated the item;
- chain, address, and note are shown.

List:

```text
/watchlist
```

Expected:

- item appears with first snapshot data if Dexscreener had data;
- output includes analyze and remove hints.

Check:

```text
/checkwatch
```

Expected:

- bot compares current metrics against first snapshot;
- output includes since-added deltas and current risk/signal fields;
- invalid or no-data entries should report status, not crash.

Refresh:

```text
/refreshwatch
```

Expected:

- bot reports updated and failed counts.

Remove:

```text
/unwatch TOKEN_ADDRESS
```

Expected:

- bot reports removed count;
- `/watchlist` no longer shows the item.

## Walletlist

Use a public wallet/address suitable for Arkham lookup.

Check one wallet:

```text
/wallet WALLET_ADDRESS
```

Expected:

- bot acknowledges Arkham wallet/address intel check;
- response includes chain rows, label/entity if available, checked time, and usage info;
- if Arkham has no data, bot returns a clear no-data or request-failed message.

Check manual wallet flow:

```text
/walletflow WALLET_ADDRESS 24h
```

Expected:

- bot acknowledges Arkham wallet flow check;
- response includes endpoint name, flow rows or no-data text, and Arkham usage;
- 400/403/404/429/500 responses are shown as readable errors and the bot keeps running;
- command only runs when typed manually.

Check manual token flow:

```text
/tokenflow solana TOKEN_ADDRESS 7d
```

Specific smoke test:

```text
/tokenflow solana CGEDT9QZDvvH5GmVkWJH2BXiMJqMJySC9ihWyr7Spump 7d
```

Expected:

- bot acknowledges Arkham token top-flow check;
- response includes chain, token address, endpoint name, top-flow rows or no-data text, and Arkham usage;
- response says `Total items from Arkham: N` or `Total items from Arkham: n/a`;
- response says `Enriched: first 10 addresses only`;
- first 10 flow addresses are enriched with Arkham label/entity data when available;
- enrichment makes up to 10 additional Arkham address lookups per `/tokenflow` call, so this command stays manual;
- enriched rows include `Type:` and `Action:` classification fields;
- Jupiter/DEX/router/exchange-style infrastructure is classified as `Infrastructure / Ignore` and is not treated as a smart-money wallet;
- `Program / Ignore` and `Infrastructure / Ignore` rows include `/wallet ADDRESS` but do not include `/watchwallet`;
- `Known Entity / Review` and `Unknown Candidate / Manual Check` rows include `/wallet ADDRESS` and `/watchwallet ADDRESS tokenflow:TOKEN_ADDRESS` commands;
- response ends with summary counts for infrastructure, known entities, unknown candidates, and programs;
- endpoint errors are shown with status code and response body instead of crashing;
- command does not add anything to watchlist and does not create background monitoring.

Check manual wallet/token transfer diagnostics:

```text
/wallettx WALLET_ADDRESS TOKEN_ADDRESS
/wallettx WALLET_ADDRESS TOKEN_ADDRESS 25
/wallettx WALLET_ADDRESS TOKEN_ADDRESS 50
```

Expected:

- bot acknowledges Arkham transfers diagnostics;
- default limit is 25, requested limits above 50 are capped at 50;
- response top block includes wallet, token, `Endpoint: Arkham /transfers`, status, Arkham usage, limit, and summary;
- summary lines include total events returned, token IN count, token OUT count, first event time, last event time, unique counterparties count, and main counterparty when one clearly dominates;
- event list says `Showing first 20 events only`, even when requested limit is 50;
- event rows are strictly compact one-line rows like `#1 2026-05-07T18:45:29Z | IN | CP: J9LUSq...Y1v1 | tx: 5CJEF...RPpD`;
- event rows do not repeat token, raw keys, owner fields, or full from/to addresses;
- event list remains newest-first as returned by Arkham;
- response includes `Potential cycles` built from a separate timestamp-ascending copy of returned events;
- cycle rows are compact, for example `#1 IN first: 2026-04-26T12:39:51Z | OUT first: 2026-04-26T12:44:07Z | IN: 1 | OUT: 2`;
- if more than 10 cycles are detected, response says `Showing first 10 cycles only`;
- if Arkham returns no data or needs different parameters, response shows a readable no-data or error message;
- command does not recommend entry/exit decisions;
- command does not calculate profit or exit quality;
- command does not add anything to watchlist and does not create background monitoring.

Check manual wallet/token trade pattern MVP:

```text
/wallettrade WALLET_ADDRESS TOKEN_ADDRESS
```

Expected:

- bot acknowledges wallet trade pattern analysis;
- response header says `Wallet Trade Pattern` and includes compact wallet, compact token, status, and Arkham usage;
- activity summary includes events analyzed, token IN count, token OUT count, active period, unique counterparties, and main counterparty;
- cycle summary includes potential cycles count, completed cycles count, average cycle duration when possible, shortest cycle, and longest cycle;
- behavior classification uses simple transfer-pattern labels such as `Active Trading Wallet`, `Accumulation / Holder`, `Distribution Only`, `Insufficient Data`, or `Pool-centric trading pattern`;
- interpretation is short and does not duplicate the summary fields;
- if `BIRDEYE_API_KEY` is missing, response keeps the behavior-only report and says `Price analysis skipped: BIRDEYE_API_KEY missing.`;
- when Birdeye candles are available, response includes `Price Movement by Cycle` with up to the latest 5 completed cycles in chronological order;
- price movement rows look like `#1 IN: time / price | OUT: time / price | Move: +X%`;
- if more than 5 completed cycles are available, response says `Analyzed latest 5 completed cycles only`;
- price movement summary includes cycles priced, positive moves, negative moves, average move, best move, and worst move;
- if a candle is missing for a cycle, that row says `price unavailable` and the bot keeps running;
- Birdeye lookup tries near timestamp first, then wider `±5 minutes` and `±15 minutes` windows if needed;
- `/wallettrade` keeps price rows compact; fallback prices may be shown with `~` before the price;
- interpretation says historical price was used when cycles are priced, or says historical price was attempted but unavailable when no selected cycles could be priced;
- limitations explicitly say no amount/usdValue is available, cycle price movement is approximate, and amount-based returns and exit quality are not calculated;
- response does not show all raw events;
- command does not recommend entry/exit decisions;
- command does not add anything to watchlist and does not create background monitoring.

Check manual Birdeye price-source diagnostic:

```text
/pricesource TOKEN_ADDRESS 2026-05-07T18:45:29Z
```

Expected:

- if `BIRDEYE_API_KEY` is missing, response says `BIRDEYE_API_KEY missing.`;
- bot acknowledges Birdeye historical price check;
- response uses the same Birdeye price result contract as `/wallettrade` and includes compact token, requested timestamp, source, endpoint, status, price near timestamp when found, candle time/open/high/low/close when available, distance, lookup window, fallback flag, raw fields count, and available keys;
- command does not calculate amount-based return, entry quality, or exit quality;
- command does not add anything to watchlist and does not create background monitoring.

Check manual parsed wallet swaps diagnostic:

```text
/walletswaps WALLET_ADDRESS
/walletswaps WALLET_ADDRESS TOKEN_ADDRESS
/walletswaps WALLET_ADDRESS TOKEN_ADDRESS 50
/walletswaps WALLET_ADDRESS TOKEN_ADDRESS 50 deep
/walletswaps WALLET_ADDRESS TOKEN_ADDRESS 50 deep10
```

Expected:

- bot acknowledges parsed wallet swaps check;
- default limit is 20, requested limits above 50 are capped at 50;
- report header includes wallet, optional token filter, mode, pages scanned, raw swaps scanned, source used, status, and items after filter;
- normal mode keeps the existing single-page behavior;
- deep mode scans Birdeye `/defi/v3/txs` with `max_pages = 5`, `page_size = 50`, `max raw events = 250`, and a 1.2 second delay between page requests;
- deep10 scans Birdeye `/defi/v3/txs` with `max_pages = 10`, `page_size = 50`, `max raw events = 500`, and a 1.2 second delay between page requests;
- if Birdeye returns 429 in deep mode, scanning stops, already found swaps are kept, header says `Rate limited: yes`, and status is readable such as `partial (rate limited 429)`;
- when token is supplied, header says `Token filter applied: yes`;
- Solscan Pro account defi activities are used when `SOLSCAN_API_KEY` is available;
- if `SOLSCAN_API_KEY` is missing or Solscan endpoint fails, report stays readable and Birdeye trades V3 fallback is attempted when `BIRDEYE_API_KEY` is available;
- summary includes total swaps, unique tokens involved, total USD value when available, most common input token, and most common output token;
- token-filtered summary includes total swaps after filter, first/last swap time, and direction counts for `token -> SOL` and `SOL -> token` when possible;
- token-filtered deep summary includes `Has possible buy` and `Has possible sell`;
- when token-filtered rows include token -> SOL sell events, response includes `Sell Window Price Check` with first sell price, last sell price, approximate price change during sell window, and total sell USD value when available;
- sell window price change is calculated as `(last_sell_price - first_sell_price) / first_sell_price * 100` using Birdeye price near each sell timestamp;
- if `BIRDEYE_API_KEY` is missing, response says `Sell window price check skipped: BIRDEYE_API_KEY missing.`;
- response includes `Swap Behavior Classification` with primary labels such as `Distribution Pattern`, `Accumulation Pattern`, `Round-trip Pattern`, `No Relevant Swaps`, or `Mixed / Needs Review`;
- classification secondary labels include `Sell-side only`, `Buy-side only`, `Two-sided activity`, `High sell pressure`, and `Weak sample`;
- evidence stays compact and may include direction counts, total swap value, and sell-window price change; this is not trading advice;
- if no normalized rows match the token filter, response says `Items returned: 0`, `Token filter applied: yes`, and `No swaps found for this wallet/token in returned window.`;
- events show at most first 20 compact rows like `#1 time | TOKEN_IN amount -> TOKEN_OUT amount | value: $X | tx: abc...xyz`;
- if both possible buy and sell are found, response says `Both possible buy and sell events found. Suitable for future wallettrade swap-cycle analysis.`;
- if only one side is found, response says only possible buy or sell events were found in the scanned window;
- if deep10 still finds no possible buy, response says `No possible buy found in scanned window. Buy may be older, routed differently, or received via transfer.`;
- response does not duplicate wallet, token, or source in each event row;
- command does not calculate amount-based return, entry/exit quality, or trading recommendations;
- command does not add anything to watchlist and does not create background monitoring.

Check manual pair+maker trades diagnostic:

```text
/pairresolve ADDRESS
/makertrades PAIR_ADDRESS MAKER_ADDRESS
/makertrades PAIR_ADDRESS MAKER_ADDRESS 50
/makertrades PAIR_ADDRESS MAKER_ADDRESS 50 deep
/makertrades PAIR_ADDRESS MAKER_ADDRESS 50 deep10
/makerfind PAIR_ADDRESS MAKER_ADDRESS
/makerfind PAIR_ADDRESS MAKER_ADDRESS deep
/makerfind PAIR_ADDRESS MAKER_ADDRESS deep50
/walletprofile WALLET_ADDRESS PAIR_ADDRESS:TOKEN_ADDRESS PAIR_ADDRESS:TOKEN_ADDRESS
/makertrades 7nvp4qykvmpeuhobyrzcn1tqiz7k8pmk5uxqeebrzyh AgmLJBMDCqWynYnQiPCuj9ewsNNsBJXyzoUhD9LJzN51 50
```

Expected:

- bot acknowledges maker trades check;
- default limit is 50, requested limits above 50 are capped at 50;
- if `BIRDEYE_API_KEY` is missing, response says `BIRDEYE_API_KEY missing`;
- report uses Birdeye `/defi/txs/pair` with `address=PAIR`, `offset=0`, `limit=1..50`, `tx_type=swap`, and `sort_type=desc`, then filters maker-like fields client-side;
- normal mode scans offset `0` only; `deep` scans up to 5 pages, `page_size = 50`, `max raw trades = 250`; `deep10` scans up to 10 pages, `page_size = 50`, `max raw trades = 500`; both deep modes wait 1.2 seconds between pages;
- report includes mode, pages scanned, raw pair trades scanned, rate limited yes/no, items from pair endpoint, items after maker filter, and `Maker filter applied: yes`;
- if Birdeye returns 429, scanning stops, found rows are preserved, and status is readable such as `partial (rate limited 429)`;
- report header includes compact pair, compact maker, source used, status, and items returned;
- if client-side maker filtering finds no rows, report includes items from pair endpoint, items after maker filter, `Maker filter applied: yes`, maker-like keys seen, and at most 3 compact pair endpoint sample rows;
- if maker is not found, response says `Maker not found in scanned pair-trade window.`;
- summary includes total trades, buy count, sell count, total buy USD, total sell USD, first trade time, last trade time, and net direction;
- behavior classification is one of `Maker Accumulation`, `Maker Distribution`, `Two-sided Active Maker`, `Weak Sample`, or `Needs More Data`;
- events show at most first 20 compact rows like `#1 time | BUY/SELL | amount token | value: $X | tx: abc...xyz`;
- response does not show raw JSON, does not calculate PnL, does not provide trading advice, and does not create background monitoring.

For `/makerfind PAIR MAKER`:

- default mode is `deep`; `deep` scans up to 20 pages, `page_size = 50`, `max raw trades = 1000`, and stops early after 20 matched maker trades;
- `deep50` scans up to 50 pages, `page_size = 50`, `max raw trades = 2500`, and stops early after 50 matched maker trades;
- both modes wait 1.2 seconds between pages and stop on 429 while preserving matched rows;
- report includes mode, source, status, pages scanned, raw pair trades scanned, matched maker trades, rate limited yes/no, buy/sell/unknown counts, first/last seen trade, first/last seen page, net direction, behavior hint, and at most first 10 matched events;
- if maker is not found, response says `Maker not found in scanned pair-trade window.`, shows maker-like keys seen, and shows up to 3 compact pair endpoint sample rows without raw JSON;
- command is a manual search tool, does not calculate PnL, does not provide trading advice, and does not create background monitoring.

For `/walletprofile WALLET PAIR:TOKEN ...`:

- command accepts up to 5 `PAIR:TOKEN` cases; invalid case format returns `Expected PAIR:TOKEN.`;
- each case uses maker-find style deep50 scan for the wallet on the pair, then Birdeye price near first/last seen timestamps for the token;
- report includes case summaries with matched trades, BUY/SELL/UNKNOWN counts, net direction, first/last seen, price movement during activity, and behavior;
- profile summary includes active cases, total matched trades, buy-heavy cases, sell-heavy cases, two-sided cases, not found cases, average price movement, and positive/negative price-window counts;
- primary wallet role is one of `Repeating Two-sided Active Maker`, `Repeating Distribution Wallet`, `Repeating Accumulation Wallet`, `Mixed Active Wallet`, or `Weak / Needs More Data`;
- response does not show raw JSON, does not calculate PnL, does not use profit/realized gain wording, does not provide trading advice, and does not create background monitoring.

For `/pairresolve ADDRESS`:

- report tries the input as both token address and pair/pool address;
- Dexscreener candidates show pair address, dex, chain, base/quote symbol/address, liquidity, and 24h volume;
- Birdeye candidates show market/pool address, source endpoint, base/quote symbol/address, liquidity, and 24h volume when available;
- recommendation says `Use this address for /makertrades: ...` when a Birdeye pool/market candidate is found;
- if no Birdeye pair candidate is found, response says `/makertrades may need Solscan/Bitquery source`;
- response does not show raw JSON, does not calculate PnL, does not provide trading advice, and does not create background monitoring.

Add:

```text
/watchwallet WALLET_ADDRESS field test
```

Expected:

- bot says it added or updated the wallet;
- address and note are shown.

List:

```text
/walletlist
```

Expected:

- wallet appears with note, first chain/label/entity when available, added time, check command, and remove command.

Check all wallets:

```text
/checkwallets
```

Expected:

- bot refreshes each wallet snapshot;
- output shows updated and failed counts;
- Arkham failures are reported without stopping the bot.

Remove:

```text
/unwatchwallet WALLET_ADDRESS
```

or:

```text
/unwatchwallet 1
```

Expected:

- bot removes the wallet by address or list number.

## Alerts

Alerts use token watchlist data and `alert_state.json`.

Manual check:

```text
/alertsnow
```

Expected:

- if there are no watched tokens, or no triggers, bot reports no new alert triggers;
- if triggers exist, alert blocks include severity title, token, chain, address, note, metrics, trigger list, analyze command, and URL;
- running the command again quickly may suppress repeated alerts because of cooldown/fingerprint logic.

Background check:

1. Ensure at least one token is in `/watchlist`.
2. Confirm `ALERT_INTERVAL_SECONDS` and `ALERT_COOLDOWN_SECONDS` in `.env`.
3. Restart the bot.
4. Wait for the startup delay and one interval.

Expected:

- alert loop starts without crashing;
- alerts are sent to `TELEGRAM_GROUP_ID` only when watched metrics cross trigger thresholds;
- no alert is acceptable if metrics are stable.

## Failure Cases To Capture

- Telegram command returns no reply after 60 seconds.
- Bot process exits or stops polling.
- Long message is cut mid-section without follow-up chunks.
- Scanner result has missing analyze/watch commands.
- `/token` invents unavailable data.
- Watchlist JSON becomes invalid or loses existing items.
- Alert repeats the same fingerprint within cooldown unexpectedly.
- Commands work outside the allowed group.
