from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup


def main_reply_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["/status", "/menu"],
            ["/micro", "/degen", "/scan", "/hot"],
            ["/watchlist", "/checkwatch"],
            ["/refreshwatch", "/alertsnow"],
            ["/watchwallet", "/walletlist", "/checkwallets"],
            ["/token", "/morning", "/evening"],
        ],
        resize_keyboard=True,
        is_persistent=False,
        one_time_keyboard=True,
    )


def main_inline_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Status", callback_data="menu:status"),
                InlineKeyboardButton("🧨 Scan Micro", callback_data="scan:micro"),
            ],
            [
                InlineKeyboardButton("🎰 Scan Degen", callback_data="scan:degen"),
                InlineKeyboardButton("🔍 Scan Normal", callback_data="scan:normal"),
            ],
            [
                InlineKeyboardButton("🔥 Hot", callback_data="scan:hot"),
            ],
            [
                InlineKeyboardButton("📋 Watchlist", callback_data="watch:list"),
                InlineKeyboardButton("🔁 Check Watch", callback_data="watch:check"),
            ],
            [
                InlineKeyboardButton("👛 Walletlist", callback_data="wallet:list"),
                InlineKeyboardButton("🔁 Check Wallets", callback_data="wallet:check"),
            ],
            [
                InlineKeyboardButton("🧪 Token Help", callback_data="menu:token_help"),
                InlineKeyboardButton("🌅 Morning", callback_data="menu:morning"),
            ],
            [
                InlineKeyboardButton("🌙 Evening", callback_data="menu:evening"),
            ],
        ]
    )


def token_chain_keyboard(address: str, detected_chain: str | None = None):
    if detected_chain == "solana":
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🧪 Analyze Solana",
                        callback_data=f"token:solana:{address}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        callback_data=f"arktoken:solana:{address}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "👛 Wallet Intel",
                        callback_data=f"wallet:{address}",
                    )
                ],

                [
                    InlineKeyboardButton(
                        "👛 Watch Wallet",
                        callback_data=f"watchwallet:{address}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "👁 Watch Solana",
                        callback_data=f"watchadd:solana:{address}",
                    )
                ],
            ]
        )

    if detected_chain == "evm":
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Analyze Base",
                        callback_data=f"token:base:{address}",
                    ),
                    InlineKeyboardButton(
                        "Analyze ETH",
                        callback_data=f"token:ethereum:{address}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "Analyze BSC",
                        callback_data=f"token:bsc:{address}",
                    ),
                    InlineKeyboardButton(
                        "Analyze ARB",
                        callback_data=f"token:arbitrum:{address}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "Watch Base",
                        callback_data=f"watchadd:base:{address}",
                    ),
                    InlineKeyboardButton(
                        "Watch ETH",
                        callback_data=f"watchadd:ethereum:{address}",
                    ),
                ],
            ]
        )

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Solana", callback_data=f"token:solana:{address}"),
                InlineKeyboardButton("Base", callback_data=f"token:base:{address}"),
            ],
            [
                InlineKeyboardButton("Ethereum", callback_data=f"token:ethereum:{address}"),
                InlineKeyboardButton("BSC", callback_data=f"token:bsc:{address}"),
            ],
        ]
    )
