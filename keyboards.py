from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup


def main_reply_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["/testsignal"],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def main_inline_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("/testsignal", callback_data="menu:testsignal_help")],
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
                        "🕵️ Arkham Intel",
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
