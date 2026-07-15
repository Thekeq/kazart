const tg = window.Telegram?.WebApp;
const config = window.APP_CONFIG || {};
const coinName = config.coinName || "coins";
const plinkoRisks = config.plinkoRisks || {};

let initData = tg?.initData || "";
let currentUser = null;
let currentBalance = null;
let currentInviteLink = "";
let currentLang = normalizeLanguage(localStorage.getItem("casinoLang") || tg?.initDataUnsafe?.user?.language_code || "ru");
let selectedUpgraderMultiplier = 1.5;
let selectedUpgradeSpeed = localStorage.getItem("casinoUpgradeSpeed") || "slow";
let selectedPlinkoRisk = "medium";
let diceDirection = "under";
let rouletteBetType = "number";
let rouletteColor = "red";
let rouletteRange = "low";
let rouletteNumber = 7;
let crashPollTimer = null;
let roulettePollTimer = null;
let activeView = "upgrader";
let crashRetryUntil = 0;
let rouletteRetryUntil = 0;
let hasCrashBet = false;
let hasRouletteBet = false;
let upgradePointerRotation = 0;
let lastHistory = [];
let lastRetention = null;
let lastShopPackages = [];
let currentStats = null;
let appLimits = { min_bet: 1, max_bet: 100000 };
let lastCrashHistory = [];
let lastRouletteHistory = [];
let lastRouletteLeaders = [];
let lastRenderedRouletteRoundId = null;
let rouletteTrackRotation = 0;
let rouletteBallRotation = 0;
let rouletteAnimatingRoundId = null;
let rouletteAnimatingUntil = 0;
let audioContext = null;
let lastCrashSoundRoundId = null;
let soundEnabled = localStorage.getItem("casinoSound") !== "off";

const rouletteOrder = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26];
const rouletteReds = new Set([1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]);

const i18n = {
  ru: {
    "auth.warning": "Открой Mini App из Telegram-бота, чтобы игровые запросы прошли проверку подписи.",
    "common.balance": "Баланс",
    "common.bet": "Ставка",
    "nav.bonus": "Бонус",
    "nav.shop": "Магазин",
    "nav.leaders": "Топ",
    "legal.strip": "Только виртуальные монеты. Без вывода, призов и реальных выигрышей.",
    "legal.terms": "Правила",
    "legal.privacy": "Приватность",
    "legal.support": "Поддержка",
    "legal.title": "Только развлечение",
    "legal.body": "KAZart использует только виртуальные монеты. Монеты не имеют денежной стоимости, их нельзя вывести, продать, передать, обменять на призы или товары.",
    "legal.point1": "Нет реальных денежных выигрышей.",
    "legal.point2": "Нет вывода средств или призов.",
    "legal.point3": "Используй только если тебе 18+.",
    "legal.accept": "Понимаю и принимаю",
    "upgrader.title": "Апгрейдер",
    "upgrader.desc": "Выбери шанс или множитель. Настройка сохранится для твоего аккаунта.",
    "upgrader.target": "Цель",
    "upgrader.chance": "Шанс",
    "upgrader.customChance": "Шанс %",
    "upgrader.customMultiplier": "Икс",
    "upgrader.presets": "Пресеты",
    "upgrader.animation": "Анимация",
    "upgrader.slow": "Медленно",
    "upgrader.fast": "Быстро",
    "upgrader.play": "Upgrade",
    "upgrader.server": "Сервер рассчитывает roll...",
    "upgrader.win": "Апгрейд прошел: выплата {amount} {coin}",
    "upgrader.lose": "Апгрейд не прошел",
    "dice.desc": "Выбери ставку, шанс и сторону.",
    "dice.chance": "Шанс",
    "dice.under": "Меньше",
    "dice.over": "Больше",
    "dice.play": "Бросить",
    "dice.roll": "Бросаем число от 1 до 100...",
    "dice.win": "Выигрыш {amount} {coin}. Выпало {roll}.",
    "dice.lose": "Проигрыш. Выпало {roll}.",
    "plinko.desc": "Центр выпадает чаще и платит меньше. Края редкие.",
    "plinko.risk": "Риск",
    "plinko.drop": "Шарик падает...",
    "plinko.result": "{risk}: слот x{multiplier}. Выплата {amount} {coin}.",
    "risk.low": "Низкий",
    "risk.medium": "Средний",
    "risk.high": "Высокий",
    "risk.degen": "Азарт",
    "crash.desc": "Один общий раунд для всех игроков.",
    "crash.status": "Статус",
    "crash.countdown": "До старта",
    "crash.players": "Игроков",
    "crash.bet": "Поставить",
    "crash.cashout": "Забрать",
    "crash.history": "Прошлые раунды",
    "crash.historyHint": "последние crash",
    "crash.leaderboard": "Топ ставок",
    "crash.waiting": "Ожидание",
    "crash.accepting": "Прием ставок",
    "crash.running": "Раунд идет",
    "crash.adding": "Ставка добавляется...",
    "crash.accepted": "Ставка принята.",
    "crash.cashed": "Забрано {amount} {coin} на x{multiplier}",
    "crash.crashed": "Раунд упал на x{multiplier}",
    "crash.noBets": "Ставок пока нет",
    "crash.noHistory": "Истории пока нет",
    "crash.inGame": "в игре",
    "roulette.desc": "Общий раунд на 37 чисел. Угадай число и получи x36.",
    "roulette.number": "Число 0-36",
    "roulette.bet": "Поставить",
    "roulette.history": "История",
    "roulette.result": "Выпало",
    "roulette.spin": "Ставка принята. Ждем результат.",
    "roulette.rolling": "Колесо крутится...",
    "roulette.win": "Выпало {number}. Выигрыш {amount} {coin}.",
    "roulette.lose": "Выпало {number}. Не угадал.",
    "bonus.title": "Бонус",
    "bonus.desc": "Забирай ежедневный бонус — серия дней увеличивает награду до 1900 монет.",
    "bonus.claim": "Забрать бонус",
    "bonus.ready": "Бонус доступен",
    "bonus.wait": "Следующий бонус через {time}",
    "wheel.title": "Колесо фортуны",
    "wheel.desc": "Бесплатный спин каждые 12 часов — даже с нулевым балансом.",
    "wheel.spin": "Крутить",
    "wheel.ready": "Спин доступен!",
    "wheel.wait": "Следующий спин через {time}",
    "wheel.won": "Выпало {amount} {coin}!",
    "bonus.claimed": "Бонус начислен: +{amount} {coin}",
    "invite.title": "Приглашай друзей",
    "invite.desc": "За каждого приглашенного друга ты получишь 1000 монет.",
    "invite.copy": "Скопировать ссылку",
    "invite.copied": "Ссылка скопирована",
    "shop.title": "Магазин",
    "shop.desc": "Telegram Stars открывают цифровые функции: косметику, Premium, Season Pass и renew daily bonus. Шансы и выплаты не меняются.",
    "shop.buy": "{stars} Stars",
  "shop.invoiceOpened": "Счет открыт. После оплаты покупка применится в Mini App.",
    "shop.renewTitle": "Обновить ежедневный бонус",
    "shop.renewDesc": "Сбросить 24-часовой таймер бонуса и забрать его раньше. Монеты остаются невыводимыми.",
    "shop.renewed": "Счет открыт. После оплаты бонус можно будет забрать снова.",
    "leaders.title": "Лидерборд",
    "leaders.desc": "Топ 100 пользователей по балансу.",
    "leaders.refresh": "Обновить"
  },
  uk: {},
  en: {}
};

i18n.uk = { ...i18n.ru,
  "upgrader.title": "Апгрейдер", "upgrader.desc": "Обери шанс або множник. Налаштування збережеться для акаунта.",
  "upgrader.target": "Ціль", "upgrader.chance": "Шанс", "upgrader.customChance": "Шанс %", "upgrader.customMultiplier": "Ікс",
  "upgrader.presets": "Пресети", "upgrader.animation": "Анімація", "upgrader.slow": "Повільно", "upgrader.fast": "Швидко",
  "dice.desc": "Обери ставку, шанс і сторону.", "dice.under": "Менше", "dice.over": "Більше", "dice.play": "Кинути",
  "plinko.risk": "Ризик", "risk.low": "Низький", "risk.medium": "Середній", "risk.high": "Високий",
  "crash.status": "Статус", "crash.countdown": "До старту", "crash.players": "Гравців", "crash.bet": "Поставити", "crash.cashout": "Забрати",
  "roulette.number": "Число 0-36", "roulette.result": "Випало", "roulette.rolling": "Колесо крутиться...", "bonus.claim": "Забрати бонус", "invite.copy": "Скопіювати посилання",
  "shop.title": "Магазин", "leaders.title": "Лідерборд", "leaders.refresh": "Оновити"
};
i18n.en = { ...i18n.ru,
  "auth.warning": "Open the Mini App from Telegram so game requests pass signature validation.",
  "common.balance": "Balance", "common.bet": "Bet", "nav.bonus": "Bonus", "nav.shop": "Shop", "nav.leaders": "Top",
  "legal.strip": "Virtual coins only. No cash out, no prizes, no real-money winnings.",
  "legal.terms": "Terms",
  "legal.privacy": "Privacy",
  "legal.support": "Support",
  "legal.title": "Entertainment only",
  "legal.body": "KAZart uses virtual coins only. Coins have no cash value, cannot be withdrawn, sold, transferred, exchanged for prizes, or redeemed for goods.",
  "legal.point1": "No real-money winnings.",
  "legal.point2": "No cash out or prizes.",
  "legal.point3": "Use only if you are 18+.",
  "legal.accept": "I understand and agree",
  "upgrader.title": "Upgrader", "upgrader.desc": "Choose chance or multiplier. The target is saved to your account.",
  "upgrader.target": "Target", "upgrader.chance": "Chance", "upgrader.customChance": "Chance %", "upgrader.customMultiplier": "X",
  "upgrader.presets": "Presets", "upgrader.animation": "Animation", "upgrader.slow": "Slow", "upgrader.fast": "Fast",
  "dice.desc": "Choose bet, chance and side.", "dice.under": "Under", "dice.over": "Over", "dice.play": "Roll",
  "dice.roll": "Rolling a number from 1 to 100...", "dice.win": "Win {amount} {coin}. Roll {roll}.", "dice.lose": "Loss. Roll {roll}.",
  "plinko.desc": "Middle slots hit more often and pay less. Edges are rare.", "plinko.risk": "Risk", "risk.low": "Low", "risk.medium": "Medium", "risk.high": "High", "risk.degen": "Degen",
  "crash.desc": "One shared round for all players.", "crash.status": "Status", "crash.countdown": "Starts in", "crash.players": "Players", "crash.bet": "Bet", "crash.cashout": "Cash out",
  "crash.history": "Past rounds", "crash.historyHint": "latest crash", "crash.leaderboard": "Top bets", "crash.waiting": "Waiting", "crash.accepting": "Betting", "crash.running": "Running",
  "roulette.desc": "Shared 37-number room. Hit the number and get x36.", "roulette.number": "Number 0-36", "roulette.bet": "Bet", "roulette.history": "History", "roulette.result": "Result", "roulette.rolling": "Wheel is spinning...",
  "bonus.title": "Bonus", "bonus.desc": "Claim the daily bonus — a day streak grows the reward up to 1,900 coins.", "bonus.claim": "Claim bonus", "bonus.ready": "Bonus ready", "bonus.wait": "Next bonus in {time}", "bonus.claimed": "Bonus credited: +{amount} {coin}",
  "wheel.title": "Wheel of Fortune", "wheel.desc": "Free spin every 12 hours — even with a zero balance.", "wheel.spin": "Spin", "wheel.ready": "Spin available!", "wheel.wait": "Next spin in {time}", "wheel.won": "You won {amount} {coin}!",
  "invite.title": "Invite friends", "invite.desc": "Get 1000 coins for every invited friend.", "invite.copy": "Copy link", "invite.copied": "Link copied",
  "shop.title": "Shop", "shop.desc": "Telegram Stars unlock digital features: cosmetics, Premium, Season Pass and daily bonus renewal. Odds and payouts do not change.", "leaders.title": "Leaderboard", "leaders.desc": "Top 100 users by balance.", "leaders.refresh": "Refresh"
};

Object.assign(i18n.uk, {
  "legal.strip": "Лише віртуальні монети. Без виводу, призів і реальних виграшів.",
  "legal.terms": "Правила",
  "legal.privacy": "Приватність",
  "legal.support": "Підтримка",
  "legal.title": "Тільки розвага",
  "legal.body": "KAZart використовує тільки віртуальні монети. Монети не мають грошової вартості, їх не можна вивести, продати, передати, обміняти на призи або товари.",
  "legal.point1": "Немає реальних грошових виграшів.",
  "legal.point2": "Немає виводу коштів або призів.",
  "legal.point3": "Використовуй тільки якщо тобі 18+.",
  "legal.accept": "Розумію і приймаю",
  "auth.warning": "Відкрий Mini App з Telegram-бота, щоб ігрові запити пройшли перевірку підпису.",
  "upgrader.play": "Апгрейд",
  "upgrader.server": "Сервер рахує roll...",
  "upgrader.win": "Апгрейд пройшов: виплата {amount} {coin}",
  "upgrader.lose": "Апгрейд не пройшов",
  "dice.chance": "Шанс",
  "dice.roll": "Кидаємо число від 1 до 100...",
  "dice.win": "Виграш {amount} {coin}. Випало {roll}.",
  "dice.lose": "Програш. Випало {roll}.",
  "plinko.desc": "Центр випадає частіше і платить менше. Краї рідкісні.",
  "plinko.drop": "Кулька падає...",
  "plinko.result": "{risk}: слот x{multiplier}. Виплата {amount} {coin}.",
  "risk.degen": "Азарт",
  "crash.desc": "Один спільний раунд для всіх гравців.",
  "crash.history": "Минулі раунди",
  "crash.historyHint": "останні crash",
  "crash.leaderboard": "Топ ставок",
  "crash.waiting": "Очікування",
  "crash.accepting": "Прийом ставок",
  "crash.running": "Раунд іде",
  "crash.adding": "Ставка додається...",
  "crash.accepted": "Ставку прийнято.",
  "crash.cashed": "Забрано {amount} {coin} на x{multiplier}",
  "crash.crashed": "Раунд впав на x{multiplier}",
  "crash.noBets": "Ставок поки немає",
  "crash.noHistory": "Історії поки немає",
  "crash.inGame": "у грі",
  "roulette.desc": "Спільний раунд на 37 чисел. Вгадай число і отримай x36.",
  "roulette.bet": "Поставити",
  "roulette.history": "Історія",
  "roulette.spin": "Ставку прийнято. Чекаємо результат.",
  "roulette.win": "Випало {number}. Виграш {amount} {coin}.",
  "roulette.lose": "Випало {number}. Не вгадав.",
  "bonus.title": "Бонус",
  "bonus.desc": "Забирай щоденний бонус — серія днів збільшує нагороду до 1900 монет.",
  "bonus.ready": "Бонус доступний",
  "bonus.wait": "Наступний бонус через {time}",
  "wheel.title": "Колесо фортуни",
  "wheel.desc": "Безкоштовний спін кожні 12 годин — навіть з нульовим балансом.",
  "wheel.spin": "Крутити",
  "wheel.ready": "Спін доступний!",
  "wheel.wait": "Наступний спін через {time}",
  "wheel.won": "Випало {amount} {coin}!",
  "bonus.claimed": "Бонус нараховано: +{amount} {coin}",
  "invite.title": "Запрошуй друзів",
  "invite.desc": "За кожного запрошеного друга ти отримаєш 1000 монет.",
  "invite.copied": "Посилання скопійовано",
  "shop.desc": "Telegram Stars відкривають цифрові функції: косметику, Premium, Season Pass і renew daily bonus. Шанси та виплати не змінюються.",
  "shop.invoiceOpened": "Рахунок відкрито. Після оплати покупка застосовується в Mini App.",
  "shop.renewTitle": "Оновити щоденний бонус",
  "shop.renewDesc": "Скинути 24-годинний таймер бонусу та забрати його раніше. Монети залишаються невивідними.",
  "shop.renewed": "Рахунок відкрито. Після оплати бонус можна буде забрати знову.",
  "leaders.desc": "Топ 100 користувачів за балансом."
});

Object.assign(i18n.en, {
  "upgrader.play": "Upgrade",
  "upgrader.server": "Server is calculating the roll...",
  "upgrader.win": "Upgrade succeeded: payout {amount} {coin}",
  "upgrader.lose": "Upgrade failed",
  "dice.chance": "Chance",
  "plinko.drop": "The ball is dropping...",
  "plinko.result": "{risk}: slot x{multiplier}. Payout {amount} {coin}.",
  "crash.adding": "Adding bet...",
  "crash.accepted": "Bet accepted.",
  "crash.cashed": "Cashed out {amount} {coin} at x{multiplier}",
  "crash.crashed": "Round crashed at x{multiplier}",
  "crash.noBets": "No bets yet",
  "crash.noHistory": "No history yet",
  "crash.inGame": "in game",
  "roulette.spin": "Bet accepted. Waiting for the result.",
  "roulette.win": "Number {number}. Win {amount} {coin}.",
  "roulette.lose": "Number {number}. Missed.",
  "shop.invoiceOpened": "Invoice opened. After payment, the item will be applied in the Mini App.",
  "shop.renewTitle": "Renew daily bonus",
  "shop.renewDesc": "Reset the 24h bonus timer so the bonus can be claimed again sooner. Coins stay non-redeemable.",
  "shop.renewed": "Invoice opened. After payment, you can claim the bonus again."
});

Object.assign(i18n.ru, {
  "auth.expired": "Сессия Mini App устарела. Закрой и открой приложение из бота заново.",
  "crash.crashedStatus": "Краш",
  "roulette.resultStatus": "Результат",
  "dice.multiplier": "Множитель",
  "dice.zone": "Цель",
  "dice.potential": "Возможный выигрыш",
  "roulette.potential": "Возможный выигрыш",
  "roulette.halves": "Половины",
  "roulette.dozens": "Дюжины",
  "roulette.yourBet": "Твоя ставка",
  "bigwin.title": "Вот это выигрыш!",
  "bigwin.subtitle": "Поделись победой с друзьями",
  "bigwin.share": "Поделиться",
  "bigwin.close": "Закрыть",
  "share.done": "Окно репоста открыто",
  "share.upgrader": "🎯 Поймал апгрейд x{x} в KAZart и забрал {amount} монет! Испытай удачу 👇",
  "share.dice": "🎲 Выбросил x{x} в Dice и поднял {amount} монет в KAZart! Сыграй и ты 👇",
  "share.plinko": "🟡 Шарик залетел на x{x} в Plinko — +{amount} монет в KAZart! Попробуй 👇",
  "share.crash": "🚀 Успел забрать на x{x} в Crash и поднял {amount} монет в KAZart! Слабо повторить? 👇",
  "share.roulette": "🎰 Угадал в рулетке и забрал {amount} монет (x{x}) в KAZart! Крути и ты 👇",
  "share.generic": "🔥 Поднял {amount} монет (x{x}) в KAZart! Залетай 👇",
  "share.invite": "🎮 Играю в KAZart — мини-игры прямо в Telegram. Заходи по моей ссылке, бонус получим оба! 👇",
  "invite.share": "Поделиться",
  "history.more": "Показать ещё",
  "leaders.allTime": "За всё время",
  "leaders.week": "Неделя",
  "leaders.weekHint": "Топ-3 недели получают 25 000 / 15 000 / 10 000 монет каждый понедельник.",
  "leaders.empty": "На этой неделе ещё никто не выигрывал — стань первым!",
  "shop.item.daily_bonus_renew.title": "Обновить ежедневный бонус",
  "shop.item.daily_bonus_renew.desc": "Сбросить 24-часовой таймер бонуса. Монеты напрямую не покупаются.",
  "shop.item.cosmetic_neon_theme.title": "Неоновая тема стола",
  "shop.item.cosmetic_neon_theme.desc": "Косметическая тема Mini App. Не влияет на игру.",
  "shop.item.cosmetic_gold_ball.title": "Золотой шар Plinko",
  "shop.item.cosmetic_gold_ball.desc": "Косметический скин шарика Plinko. Не влияет на игру.",
  "shop.item.premium_30d.title": "Премиум на 30 дней",
  "shop.item.premium_30d.desc": "Значок профиля, косметика и удобства. Шансы и выплаты не меняются.",
  "shop.item.season_pass.title": "Сезонный пасс",
  "shop.item.season_pass.desc": "Премиум-ветка наград сезонного трека. Шансы и выплаты не меняются.",
  "history.title": "История",
  "history.desc": "Последние игры, бонусы и изменения баланса.",
  "history.refresh": "Обновить",
  "history.empty": "Истории пока нет",
  "history.game": "Игра",
  "history.balance": "Баланс",
  "history.bet": "ставка",
  "history.payout": "выплата",
  "history.after": "баланс",
  "profile.title": "Профиль",
  "profile.desc": "Статус аккаунта, лимиты и настройки.",
  "profile.games": "Игр",
  "profile.wins": "Побед",
  "profile.totalBet": "Сумма ставок",
  "profile.best": "Лучшая выплата",
  "profile.refs": "Рефералы",
  "profile.limit": "Лимит ставки",
  "profile.status": "Статус",
  "profile.active": "Активен",
  "profile.blocked": "Заблокирован",
  "profile.bonusNotify": "Напоминания о бонусе",
  "profile.bonusNotifyDesc": "Сообщение в Telegram, когда ежедневный бонус снова доступен.",
  "profile.saved": "Настройка сохранена",
  "invite.safeDesc": "Награда за реферала начисляется после принятия им правил.",
  "onboarding.title": "Перед игрой",
  "onboarding.point1": "Монеты виртуальные: их нельзя вывести или обменять на призы.",
  "onboarding.point2": "Бонус открывается кнопкой подарка, магазин - кликом по балансу.",
  "onboarding.point3": "История и профиль есть в быстрых кнопках справа вверху.",
  "onboarding.close": "Понятно",
  "roulette.betType": "Тип ставки",
  "roulette.typeNumber": "Число",
  "roulette.typeColor": "Цвет",
  "roulette.typeRange": "Диапазон",
  "roulette.red": "Красное",
  "roulette.black": "Черное",
  "roulette.selection": "ставка {selection}",
  "retention.title": "Квесты и серии",
  "retention.desc": "Ежедневные цели, streak и season progress.",
  "retention.claim": "Забрать",
  "retention.claimed": "Забрано",
  "retention.streak": "Daily streak",
  "retention.season": "Season",
  "retention.premium": "Premium",
  "retention.cosmetics": "Косметика",
  "retention.default": "Базовый",
  "retention.cosmeticSaved": "Косметика сохранена",
  "retention.quest.daily_bonus": "Забери daily bonus",
  "retention.quest.play_5": "Сыграй 5 игр сегодня",
  "retention.quest.try_3_games": "Попробуй 3 разных игры",
  "retention.quest.roulette_room": "Сыграй Roulette room",
  "retention.quest.invite_1": "Пригласи 1 друга",
  "retention.quest.win_3": "Выиграй 3 раза сегодня",
  "retention.quest.big_win": "Выиграй с иксом x5+",
  "retention.quest.crash_cashout": "Успей забрать в Crash",
  "retention.quest.volume_1000": "Прокрути 1000 монет за день",
  "retention.quests": "Ежедневные квесты",
  "season.title": "Сезонный трек",
  "season.passHint": "★ Премиум-награды открываются с Season Pass (в магазине).",
  "season.level": "Уровень",
  "ach.title": "Ачивки",
  "ach.first_win": "Первая победа",
  "ach.games_50": "50 игр",
  "ach.games_250": "250 игр",
  "ach.games_1000": "1000 игр",
  "ach.wins_100": "100 побед",
  "ach.big_x10": "Победа с x10+",
  "ach.streak_7": "Серия 7 дней",
  "ach.streak_30": "Серия 30 дней",
  "ach.invite_3": "3 друга",
  "ach.invite_10": "10 друзей",
  "ach.all_games": "Испытай все игры",
  "ach.total_bet_100k": "Оборот 100k"
});

Object.assign(i18n.uk, {
  "auth.expired": "Сесія Mini App застаріла. Закрий і відкрий застосунок з бота знову.",
  "crash.crashedStatus": "Краш",
  "roulette.resultStatus": "Результат",
  "dice.multiplier": "Множник",
  "dice.zone": "Ціль",
  "dice.potential": "Можливий виграш",
  "roulette.potential": "Можливий виграш",
  "roulette.halves": "Половини",
  "roulette.dozens": "Дюжини",
  "roulette.yourBet": "Твоя ставка",
  "bigwin.title": "Оце виграш!",
  "bigwin.subtitle": "Поділись перемогою з друзями",
  "bigwin.share": "Поділитися",
  "bigwin.close": "Закрити",
  "share.done": "Вікно репосту відкрито",
  "share.upgrader": "🎯 Спіймав апгрейд x{x} у KAZart і забрав {amount} монет! Спробуй удачу 👇",
  "share.dice": "🎲 Викинув x{x} у Dice і підняв {amount} монет у KAZart! Зіграй і ти 👇",
  "share.plinko": "🟡 Кулька залетіла на x{x} у Plinko — +{amount} монет у KAZart! Спробуй 👇",
  "share.crash": "🚀 Встиг забрати на x{x} у Crash і підняв {amount} монет у KAZart! Слабо повторити? 👇",
  "share.roulette": "🎰 Вгадав у рулетці й забрав {amount} монет (x{x}) у KAZart! Крути і ти 👇",
  "share.generic": "🔥 Підняв {amount} монет (x{x}) у KAZart! Залітай 👇",
  "share.invite": "🎮 Граю в KAZart — міні-ігри просто в Telegram. Заходь за моїм посиланням, бонус отримаємо обидва! 👇",
  "invite.share": "Поділитися",
  "history.more": "Показати ще",
  "leaders.allTime": "За весь час",
  "leaders.week": "Тиждень",
  "leaders.weekHint": "Топ-3 тижня отримують 25 000 / 15 000 / 10 000 монет щопонеділка.",
  "leaders.empty": "Цього тижня ще ніхто не вигравав — стань першим!",
  "shop.item.daily_bonus_renew.title": "Оновити щоденний бонус",
  "shop.item.daily_bonus_renew.desc": "Скинути 24-годинний таймер бонусу. Монети напряму не купуються.",
  "shop.item.cosmetic_neon_theme.title": "Неонова тема столу",
  "shop.item.cosmetic_neon_theme.desc": "Косметична тема Mini App. Не впливає на гру.",
  "shop.item.cosmetic_gold_ball.title": "Золота кулька Plinko",
  "shop.item.cosmetic_gold_ball.desc": "Косметичний скін кульки Plinko. Не впливає на гру.",
  "shop.item.premium_30d.title": "Преміум на 30 днів",
  "shop.item.premium_30d.desc": "Значок профілю, косметика та зручності. Шанси та виплати не змінюються.",
  "shop.item.season_pass.title": "Сезонний пас",
  "shop.item.season_pass.desc": "Преміум-гілка нагород сезонного треку. Шанси та виплати не змінюються.",
  "history.title": "Історія",
  "history.desc": "Останні ігри, бонуси та зміни балансу.",
  "history.refresh": "Оновити",
  "history.empty": "Історії поки немає",
  "history.game": "Гра",
  "history.balance": "Баланс",
  "history.bet": "ставка",
  "history.payout": "виплата",
  "history.after": "баланс",
  "profile.title": "Профіль",
  "profile.desc": "Статус акаунта, ліміти та налаштування.",
  "profile.games": "Ігор",
  "profile.wins": "Перемог",
  "profile.totalBet": "Сума ставок",
  "profile.best": "Найкраща виплата",
  "profile.refs": "Реферали",
  "profile.limit": "Ліміт ставки",
  "profile.status": "Статус",
  "profile.active": "Активний",
  "profile.blocked": "Заблокований",
  "profile.bonusNotify": "Нагадування про бонус",
  "profile.bonusNotifyDesc": "Повідомлення в Telegram, коли щоденний бонус знову доступний.",
  "profile.saved": "Налаштування збережено",
  "invite.safeDesc": "Нагорода за реферала нараховується після прийняття ним правил.",
  "onboarding.title": "Перед грою",
  "onboarding.point1": "Монети віртуальні: їх не можна вивести або обміняти на призи.",
  "onboarding.point2": "Бонус відкривається кнопкою подарунка, магазин - кліком по балансу.",
  "onboarding.point3": "Історія і профіль є у швидких кнопках справа вгорі.",
  "onboarding.close": "Зрозуміло",
  "roulette.betType": "Тип ставки",
  "roulette.typeNumber": "Число",
  "roulette.typeColor": "Колір",
  "roulette.typeRange": "Діапазон",
  "roulette.red": "Червоне",
  "roulette.black": "Чорне",
  "roulette.selection": "ставка {selection}",
  "retention.title": "Квести і серії",
  "retention.desc": "Щоденні цілі, streak і season progress.",
  "retention.claim": "Забрати",
  "retention.claimed": "Забрано",
  "retention.streak": "Daily streak",
  "retention.season": "Season",
  "retention.premium": "Premium",
  "retention.cosmetics": "Косметика",
  "retention.default": "Базовий",
  "retention.cosmeticSaved": "Косметику збережено",
  "retention.quest.daily_bonus": "Забери daily bonus",
  "retention.quest.play_5": "Зіграй 5 ігор сьогодні",
  "retention.quest.try_3_games": "Спробуй 3 різні ігри",
  "retention.quest.roulette_room": "Зіграй Roulette room",
  "retention.quest.invite_1": "Запроси 1 друга",
  "retention.quest.win_3": "Виграй 3 рази сьогодні",
  "retention.quest.big_win": "Виграй з іксом x5+",
  "retention.quest.crash_cashout": "Встигни забрати в Crash",
  "retention.quest.volume_1000": "Прокрути 1000 монет за день",
  "retention.quests": "Щоденні квести",
  "season.title": "Сезонний трек",
  "season.passHint": "★ Преміум-нагороди відкриваються з Season Pass (у магазині).",
  "season.level": "Рівень",
  "ach.title": "Ачивки",
  "ach.first_win": "Перша перемога",
  "ach.games_50": "50 ігор",
  "ach.games_250": "250 ігор",
  "ach.games_1000": "1000 ігор",
  "ach.wins_100": "100 перемог",
  "ach.big_x10": "Перемога з x10+",
  "ach.streak_7": "Серія 7 днів",
  "ach.streak_30": "Серія 30 днів",
  "ach.invite_3": "3 друзі",
  "ach.invite_10": "10 друзів",
  "ach.all_games": "Випробуй всі ігри",
  "ach.total_bet_100k": "Оборот 100k"
});

Object.assign(i18n.en, {
  "auth.expired": "The Mini App session expired. Close and reopen the app from the bot.",
  "crash.crashedStatus": "Crashed",
  "roulette.resultStatus": "Result",
  "dice.multiplier": "Multiplier",
  "dice.zone": "Target",
  "dice.potential": "Potential win",
  "roulette.potential": "Potential win",
  "roulette.halves": "Halves",
  "roulette.dozens": "Dozens",
  "roulette.yourBet": "Your bet",
  "bigwin.title": "Massive win!",
  "bigwin.subtitle": "Share your win with friends",
  "bigwin.share": "Share",
  "bigwin.close": "Close",
  "share.done": "Share sheet opened",
  "share.upgrader": "🎯 Hit a x{x} upgrade on KAZart and grabbed {amount} coins! Try your luck 👇",
  "share.dice": "🎲 Rolled x{x} on Dice for {amount} coins on KAZart! Give it a spin 👇",
  "share.plinko": "🟡 Dropped into x{x} on Plinko — +{amount} coins on KAZart! Try it 👇",
  "share.crash": "🚀 Cashed out at x{x} on Crash for {amount} coins on KAZart! Beat that 👇",
  "share.roulette": "🎰 Nailed the roulette for {amount} coins (x{x}) on KAZart! Spin it 👇",
  "share.generic": "🔥 Won {amount} coins (x{x}) on KAZart! Come play 👇",
  "share.invite": "🎮 I'm playing KAZart — mini-games right inside Telegram. Join via my link and we both get a bonus! 👇",
  "invite.share": "Share",
  "history.more": "Show more",
  "leaders.allTime": "All time",
  "leaders.week": "This week",
  "leaders.weekHint": "Weekly top-3 get 25,000 / 15,000 / 10,000 coins every Monday.",
  "leaders.empty": "No winners this week yet — be the first!",
  "shop.item.daily_bonus_renew.title": "Renew daily bonus",
  "shop.item.daily_bonus_renew.desc": "Reset the 24h bonus timer. This does not buy coins directly.",
  "shop.item.cosmetic_neon_theme.title": "Neon table theme",
  "shop.item.cosmetic_neon_theme.desc": "Cosmetic Mini App theme. No gameplay advantage.",
  "shop.item.cosmetic_gold_ball.title": "Gold Plinko ball",
  "shop.item.cosmetic_gold_ball.desc": "Cosmetic Plinko ball skin. No gameplay advantage.",
  "shop.item.premium_30d.title": "Premium 30 days",
  "shop.item.premium_30d.desc": "Profile badge, cosmetics and convenience. Odds and payouts do not change.",
  "shop.item.season_pass.title": "Season pass",
  "shop.item.season_pass.desc": "Premium tier of the season reward track. Odds and payouts do not change.",
  "history.title": "History",
  "history.desc": "Recent games, bonuses and balance changes.",
  "history.refresh": "Refresh",
  "history.empty": "No history yet",
  "history.game": "Game",
  "history.balance": "Balance",
  "history.bet": "bet",
  "history.payout": "payout",
  "history.after": "balance",
  "profile.title": "Profile",
  "profile.desc": "Account status, limits and preferences.",
  "profile.games": "Games",
  "profile.wins": "Wins",
  "profile.totalBet": "Total bet",
  "profile.best": "Best payout",
  "profile.refs": "Referrals",
  "profile.limit": "Bet limit",
  "profile.status": "Status",
  "profile.active": "Active",
  "profile.blocked": "Blocked",
  "profile.bonusNotify": "Daily bonus reminders",
  "profile.bonusNotifyDesc": "Telegram notification when the daily bonus is ready.",
  "profile.saved": "Setting saved",
  "invite.safeDesc": "Referral reward is credited after the invited user accepts the virtual-only rules.",
  "onboarding.title": "Before you play",
  "onboarding.point1": "Coins are virtual and cannot be cashed out or exchanged for prizes.",
  "onboarding.point2": "Use the gift button for the daily bonus and the balance button for the shop.",
  "onboarding.point3": "History and profile are in the top-right quick actions.",
  "onboarding.close": "Got it",
  "roulette.betType": "Bet type",
  "roulette.typeNumber": "Number",
  "roulette.typeColor": "Color",
  "roulette.typeRange": "Range",
  "roulette.red": "Red",
  "roulette.black": "Black",
  "roulette.selection": "bet {selection}",
  "retention.title": "Quests and streaks",
  "retention.desc": "Daily goals, streaks and season progress.",
  "retention.claim": "Claim",
  "retention.claimed": "Claimed",
  "retention.streak": "Daily streak",
  "retention.season": "Season",
  "retention.premium": "Premium",
  "retention.cosmetics": "Cosmetics",
  "retention.default": "Default",
  "retention.cosmeticSaved": "Cosmetic saved",
  "retention.quest.daily_bonus": "Claim daily bonus",
  "retention.quest.play_5": "Play 5 games today",
  "retention.quest.try_3_games": "Try 3 different games",
  "retention.quest.roulette_room": "Play Roulette room",
  "retention.quest.invite_1": "Invite 1 friend",
  "retention.quest.win_3": "Win 3 games today",
  "retention.quest.big_win": "Win with a x5+ multiplier",
  "retention.quest.crash_cashout": "Cash out in Crash",
  "retention.quest.volume_1000": "Wager 1000 coins today",
  "retention.quests": "Daily quests",
  "season.title": "Season track",
  "season.passHint": "★ Premium rewards unlock with the Season Pass (shop).",
  "season.level": "Level",
  "ach.title": "Achievements",
  "ach.first_win": "First win",
  "ach.games_50": "50 games",
  "ach.games_250": "250 games",
  "ach.games_1000": "1000 games",
  "ach.wins_100": "100 wins",
  "ach.big_x10": "Win with x10+",
  "ach.streak_7": "7-day streak",
  "ach.streak_30": "30-day streak",
  "ach.invite_3": "3 friends",
  "ach.invite_10": "10 friends",
  "ach.all_games": "Try every game",
  "ach.total_bet_100k": "100k wagered"
});

if (tg) {
  tg.ready();
  tg.expand();
  tg.setHeaderColor("#101014");
  tg.setBackgroundColor("#101014");
  try { tg.enableClosingConfirmation?.(); } catch (_) {}
}

function haptic(kind) {
  const feedback = tg?.HapticFeedback;
  if (!feedback) return;
  try {
    if (kind === "win") feedback.notificationOccurred("success");
    else if (kind === "lose" || kind === "crash") feedback.notificationOccurred("error");
    else if (kind === "bet") feedback.impactOccurred("medium");
    else feedback.impactOccurred("light");
  } catch (_) {}
}

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function getAudioContext() {
  if (!window.AudioContext && !window.webkitAudioContext) return null;
  if (!audioContext) audioContext = new (window.AudioContext || window.webkitAudioContext)();
  if (audioContext.state === "suspended") audioContext.resume().catch(() => {});
  return audioContext;
}

document.addEventListener("pointerdown", () => getAudioContext(), { once: true, passive: true });

function playTone(frequency, duration = 0.08, options = {}) {
  if (!soundEnabled) return;
  const ctx = getAudioContext();
  if (!ctx) return;
  const delay = Number(options.delay || 0);
  const start = ctx.currentTime + delay;
  const end = start + duration;
  const oscillator = ctx.createOscillator();
  const gain = ctx.createGain();
  oscillator.type = options.type || "sine";
  oscillator.frequency.setValueAtTime(Math.max(20, frequency), start);
  if (options.endFrequency) {
    oscillator.frequency.exponentialRampToValueAtTime(Math.max(20, options.endFrequency), end);
  }
  gain.gain.setValueAtTime(Number(options.volume || 0.045), start);
  gain.gain.exponentialRampToValueAtTime(0.001, end);
  oscillator.connect(gain);
  gain.connect(ctx.destination);
  oscillator.start(start);
  oscillator.stop(end + 0.02);
}

function playSound(name, options = {}) {
  haptic(name);
  const duration = Number(options.duration || 0);
  if (name === "click") playTone(420, 0.045, { type: "square", volume: 0.025 });
  if (name === "bet") {
    playTone(360, 0.045, { type: "triangle", volume: 0.03 });
    playTone(560, 0.06, { delay: 0.045, type: "triangle", volume: 0.035 });
  }
  if (name === "roll") {
    [0, 0.055, 0.11, 0.165].forEach((delay, index) => playTone(430 + index * 80, 0.035, { delay, type: "square", volume: 0.025 }));
  }
  if (name === "spin") {
    const count = Math.min(28, Math.max(7, Math.floor(duration / 240)));
    for (let i = 0; i < count; i += 1) {
      playTone(260 + (i % 5) * 52, 0.03, { delay: i * 0.18, type: "square", volume: 0.018 });
    }
  }
  if (name === "slot") {
    playTone(640, 0.055, { type: "triangle", volume: 0.035 });
    playTone(860, 0.07, { delay: 0.055, type: "triangle", volume: 0.04 });
  }
  if (name === "win") {
    [523, 659, 784, 1046].forEach((frequency, index) => playTone(frequency, 0.09, { delay: index * 0.085, type: "triangle", volume: 0.045 }));
  }
  if (name === "lose") {
    playTone(260, 0.12, { type: "sawtooth", volume: 0.035, endFrequency: 150 });
    playTone(180, 0.11, { delay: 0.11, type: "sawtooth", volume: 0.028, endFrequency: 120 });
  }
  if (name === "crash") {
    playTone(180, 0.26, { type: "sawtooth", volume: 0.05, endFrequency: 55 });
    playTone(90, 0.16, { delay: 0.05, type: "square", volume: 0.025, endFrequency: 45 });
  }
}

function t(key, vars = {}) {
  const template = i18n[currentLang]?.[key] || i18n.ru[key] || key;
  return template.replace(/\{(\w+)\}/g, (_, name) => vars[name] ?? "");
}

function normalizeLanguage(lang) {
  const short = String(lang || "ru").toLowerCase().slice(0, 2);
  return ["uk", "en", "ru"].includes(short) ? short : "ru";
}

function applyLanguage(lang) {
  currentLang = normalizeLanguage(lang);
  localStorage.setItem("casinoLang", currentLang);
  document.documentElement.lang = currentLang;
  $$("[data-i18n]").forEach((node) => {
    const text = t(node.dataset.i18n);
    node.textContent = text;
    if (node.dataset.originalText) node.dataset.originalText = text;
  });
  $$(".language-switch button").forEach((button) => button.classList.toggle("active", button.dataset.lang === currentLang));
  if (currentBalance !== null && currentBalance !== undefined) setBalance(currentBalance);
  renderCrashHistory(lastCrashHistory);
  renderRouletteHistory(lastRouletteHistory);
  renderRouletteLeaderboard(lastRouletteLeaders);
  renderHistory(lastHistory);
  renderRetention(lastRetention);
  if (lastShopPackages.length) renderShopPackages(lastShopPackages, false);
  renderProfile();
  if ($("#rouletteSelectionText")) updateRouletteSummary();
}

function localeTag() {
  return currentLang === "en" ? "en-US" : currentLang === "uk" ? "uk-UA" : "ru-RU";
}

function formatNumber(value, digits = 0) {
  return Number(value || 0).toLocaleString(localeTag(), { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function fmtTime(seconds) {
  seconds = Math.max(0, Math.floor(Number(seconds || 0)));
  const units = currentLang === "en" ? ["h", "m", "s"] : currentLang === "uk" ? ["год", "хв", "с"] : ["ч", "м", "с"];
  const gap = currentLang === "en" ? "" : " ";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}${gap}${units[0]} ${m}${gap}${units[1]}`;
  if (m > 0) return `${m}${gap}${units[1]}`;
  return `${seconds % 60}${gap}${units[2]}`;
}

function setBusy(button, busy) {
  button.disabled = busy;
  button.dataset.originalText ||= button.textContent;
  button.textContent = busy ? "..." : button.dataset.originalText;
}

let balancePulseTimer = null;
function setBalance(value) {
  if (value === undefined || value === null) return;
  const previous = currentBalance;
  currentBalance = value;
  $("#balance").textContent = formatNumber(value);
  if (previous !== null && Number(value) !== Number(previous)) {
    const pill = $(".balance-pill");
    if (pill) {
      pill.classList.remove("balance-up", "balance-down");
      void pill.offsetWidth;
      pill.classList.add(Number(value) > Number(previous) ? "balance-up" : "balance-down");
      clearTimeout(balancePulseTimer);
      balancePulseTimer = setTimeout(() => pill.classList.remove("balance-up", "balance-down"), 700);
    }
  }
}

function showResult(target, text, win) {
  const state = win === true ? "win" : win === false ? "lose" : "neutral";
  if (target.textContent === text && target.dataset.resultState === state) return;
  target.dataset.resultState = state;
  target.textContent = text;
  target.classList.toggle("win", Boolean(win));
  target.classList.toggle("lose", win === false);
  target.classList.remove("result-flash");
  void target.offsetWidth;
  target.classList.add("result-flash");
}

function showAuthExpired() {
  const warning = $("#authWarning");
  if (!warning) return;
  warning.dataset.i18n = "auth.expired";
  warning.textContent = t("auth.expired");
  warning.hidden = false;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", "X-Telegram-Init-Data": initData, ...(options.headers || {}) }
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.ok === false) {
    if (response.status === 401 && initData) showAuthExpired();
    const error = new Error(body.error || `HTTP ${response.status}`);
    error.status = response.status;
    error.retryAfter = Number(body.retry_after || response.headers.get("Retry-After") || 0);
    throw error;
  }
  return body;
}

async function loadMe() {
  if (!initData) {
    $("#authWarning").hidden = false;
    renderShopPackages([{ kind: "daily_bonus_renew", stars: 25 }]);
    return;
  }
  try {
    const body = await api("/api/me");
    currentUser = body.user;
    currentStats = body.stats || null;
    appLimits = body.limits || appLimits;
    setBalance(body.user.balance);
    renderLegalGate(body.user);
    currentInviteLink = body.invite_link || "";
    $("#inviteLink").value = currentInviteLink;
    $("#profileInviteLink").value = currentInviteLink;
    applyUpgraderSettingsFromUser(body.user);
    renderBonus(body.bonus);
    if (body.wheel) renderWheel(body.wheel);
    renderProfile();
    maybeShowOnboarding(body.user);
    loadShopPackages();
    loadLeaderboard();
    if (body.user.legal_accepted_at) loadRetention();
  } catch (error) {
    $("#authWarning").hidden = false;
    showResult($("#upgraderResult"), error.message, false);
  }
}

function renderLegalGate(user) {
  const accepted = Boolean(user?.legal_accepted_at);
  $("#legalModal").hidden = accepted;
}

function openView(viewName) {
  const target = $(`#view-${viewName}`);
  if (!target) return;
  activeView = viewName;
  playSound("click");
  $$(".tab").forEach((item) => item.classList.toggle("active", item.dataset.tab === viewName));
  $$(".game-view").forEach((view) => view.classList.remove("active"));
  target.classList.add("active");
  syncLivePolling();
  if (viewName === "leaders") loadLeaderboard();
  if (viewName === "history") loadHistory();
  if (viewName === "profile") loadProfile();
  if (viewName === "retention") loadRetention();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function bindBetSteppers() {
  $$(".bet-step").forEach((button) => {
    button.addEventListener("click", () => {
      const input = document.getElementById(button.dataset.betTarget);
      if (!input) return;
      playSound("click");
      const current = Math.max(1, Number(input.value) || Number(appLimits.min_bet) || 1);
      const next = button.dataset.betStep === "half" ? Math.floor(current / 2) : current * 2;
      const min = Number(appLimits.min_bet) || 1;
      const max = Number(appLimits.max_bet) || 100000;
      const clamped = Math.max(min, Math.min(max, next));
      const capped = currentBalance !== null ? Math.min(clamped, Math.max(min, Math.floor(currentBalance))) : clamped;
      input.value = String(capped);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
  });
}

function bindTabs() {
  $$(".tab").forEach((button) => {
    button.addEventListener("click", () => openView(button.dataset.tab));
  });
}

function bindViewOpeners() {
  $$("[data-open-view]").forEach((button) => {
    button.addEventListener("click", () => openView(button.dataset.openView));
  });
}

function syncLivePolling() {
  if (activeView === "crash") {
    startCrashPolling();
  } else {
    stopCrashPolling();
  }
  if (activeView === "roulette") {
    startRoulettePolling();
  } else {
    stopRoulettePolling();
  }
}

function bindLanguageSwitch() {
  $$(".language-switch button").forEach((button) => button.addEventListener("click", () => applyLanguage(button.dataset.lang)));
  applyLanguage(currentLang);
}

function bindSoundToggle() {
  const button = $("#toggleSound");
  const render = () => {
    button.classList.toggle("sound-off", !soundEnabled);
    button.setAttribute("aria-label", soundEnabled ? "Mute sound" : "Unmute sound");
  };
  button.addEventListener("click", () => {
    soundEnabled = !soundEnabled;
    localStorage.setItem("casinoSound", soundEnabled ? "on" : "off");
    if (soundEnabled) playSound("click");
    render();
  });
  render();
}

function bindLegalGate() {
  $("#acceptLegal").addEventListener("click", async () => {
    setBusy($("#acceptLegal"), true);
    try {
      if (initData) {
        const body = await api("/api/legal/accept", { method: "POST" });
        currentUser = body.user;
        renderProfile();
      }
      $("#legalModal").hidden = true;
      maybeShowOnboarding(currentUser);
      playSound("click");
    } catch (error) {
      showResult($("#authWarning"), error.message, false);
      $("#authWarning").hidden = false;
    } finally {
      setBusy($("#acceptLegal"), false);
    }
  });
}

function chanceFromMultiplier(multiplier) {
  return Math.min(75, Math.max(0.01, 96 / Number(multiplier || 1)));
}

function multiplierFromChance(chance) {
  return 96 / Math.min(75, Math.max(0.01, Number(chance || 1)));
}

function applyUpgraderSettingsFromUser(user) {
  const multiplier = Number(user?.upgrader_multiplier || 1.5);
  const chance = Number(user?.upgrader_chance || chanceFromMultiplier(multiplier));
  selectedUpgraderMultiplier = multiplier;
  $("#upgraderCustomMultiplier").value = multiplier.toFixed(multiplier >= 100 ? 2 : 4).replace(/\.?0+$/, "");
  $("#upgraderCustomChance").value = chance.toFixed(2).replace(/\.?0+$/, "");
  updateUpgraderQuote();
}

function updateUpgraderQuote() {
  const bet = Number($("#upgraderBet").value || 0);
  const chance = Math.min(75, Math.max(0.01, Number($("#upgraderCustomChance").value || 1)));
  selectedUpgraderMultiplier = multiplierFromChance(chance);
  const chanceDeg = Math.max(1, Math.min(359, chance * 3.6));
  $("#upgraderStakePreview").textContent = formatNumber(bet);
  $("#upgraderChance").textContent = `${chance.toFixed(2)}%`;
  $("#upgraderWin").textContent = formatNumber(Math.floor(bet * selectedUpgraderMultiplier));
  $("#upgraderDial").style.setProperty("--green-start", `${180 - chanceDeg / 2}deg`);
  $("#upgraderDial").style.setProperty("--green-end", `${180 + chanceDeg / 2}deg`);
}

let saveUpgraderTimer = null;
function scheduleSaveUpgraderSettings() {
  clearTimeout(saveUpgraderTimer);
  saveUpgraderTimer = setTimeout(async () => {
    if (!initData) return;
    try {
      await api("/api/settings/upgrader", { method: "POST", body: JSON.stringify({ chance: Number($("#upgraderCustomChance").value) }) });
    } catch (_) {}
  }, 500);
}

function bindUpgrader() {
  $("#upgraderBet").addEventListener("input", updateUpgraderQuote);
  $("#upgraderCustomChance").addEventListener("input", () => {
    const chance = Math.min(75, Math.max(0.01, Number($("#upgraderCustomChance").value || 1)));
    $("#upgraderCustomMultiplier").value = multiplierFromChance(chance).toFixed(4).replace(/\.?0+$/, "");
    updateUpgraderQuote();
    scheduleSaveUpgraderSettings();
  });
  $("#upgraderCustomMultiplier").addEventListener("input", () => {
    const multiplier = Math.max(1.28, Number($("#upgraderCustomMultiplier").value || 1.28));
    $("#upgraderCustomChance").value = chanceFromMultiplier(multiplier).toFixed(2).replace(/\.?0+$/, "");
    updateUpgraderQuote();
    scheduleSaveUpgraderSettings();
  });
  $$("#upgraderMultipliers button").forEach((button) => {
    button.addEventListener("click", () => {
      playSound("click");
      const multiplier = Number(button.dataset.multiplier);
      $("#upgraderCustomMultiplier").value = String(multiplier);
      $("#upgraderCustomChance").value = chanceFromMultiplier(multiplier).toFixed(2).replace(/\.?0+$/, "");
      $$("#upgraderMultipliers button").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      updateUpgraderQuote();
      scheduleSaveUpgraderSettings();
    });
  });
  $$("#upgraderSpeed button").forEach((button) => {
    button.classList.toggle("active", button.dataset.speed === selectedUpgradeSpeed);
    button.addEventListener("click", () => {
      playSound("click");
      selectedUpgradeSpeed = button.dataset.speed;
      localStorage.setItem("casinoUpgradeSpeed", selectedUpgradeSpeed);
      $$("#upgraderSpeed button").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
    });
  });
  $("#playUpgrader").addEventListener("click", playUpgrader);
  updateUpgraderQuote();
}

async function playUpgrader() {
  const button = $("#playUpgrader");
  const pointer = $("#upgraderPointer");
  let unlockDelay = 1900;
  playSound("click");
  setBusy(button, true);
  showResult($("#upgraderResult"), t("upgrader.server"), null);
  try {
    const chance = Number($("#upgraderCustomChance").value);
    const body = await api("/api/games/upgrader", { method: "POST", body: JSON.stringify({ bet: Number($("#upgraderBet").value), chance }) });
    const result = body.result;
    const chanceDeg = Math.max(1, Math.min(359, result.success_chance * 3.6));
    const greenStart = 180 - chanceDeg / 2;
    const greenEnd = 180 + chanceDeg / 2;
    const successBps = Math.max(1, Number(result.success_bps || 1));
    const finalDeg = result.roll <= successBps
      ? greenStart + (result.roll / successBps) * chanceDeg
      : greenEnd + ((result.roll - successBps) / (10000 - successBps)) * (360 - chanceDeg);
    const duration = selectedUpgradeSpeed === "slow" ? 5000 + Math.floor(Math.random() * 3001) : 1900;
    unlockDelay = duration;
    const currentNorm = ((upgradePointerRotation % 360) + 360) % 360;
    const targetRotation = upgradePointerRotation + (selectedUpgradeSpeed === "slow" ? 2160 : 1440) + ((finalDeg - currentNorm + 360) % 360);
    playSound("spin", { duration });
    pointer.animate(
      [{ transform: `translateX(-50%) rotate(${upgradePointerRotation}deg)` }, { transform: `translateX(-50%) rotate(${targetRotation}deg)` }],
      { duration, easing: "cubic-bezier(.11,.78,.14,1)", fill: "forwards" }
    );
    upgradePointerRotation = targetRotation;
    setTimeout(() => {
      setBalance(result.balance_after);
      $("#upgraderRoll").textContent = `Roll ${result.roll_percent.toFixed(2)}%`;
      showResult($("#upgraderResult"), result.success ? t("upgrader.win", { amount: formatNumber(result.win_amount), coin: coinName }) : t("upgrader.lose"), result.success);
      playSound(result.success ? "win" : "lose");
      if (result.success) registerWin("upgrader", selectedUpgraderMultiplier, result.win_amount); else clearShare("upgrader");
    }, Math.max(300, duration - 90));
  } catch (error) {
    showResult($("#upgraderResult"), error.message, false);
  } finally {
    setTimeout(() => setBusy(button, false), unlockDelay);
  }
}

const DICE_HOUSE_EDGE = 0.04;

function updateDicePreview() {
  const chance = Math.max(1, Math.min(90, Number($("#diceChance").value) || 50));
  const bet = Math.max(0, Number($("#diceBet").value) || 0);
  const multiplier = (100 / chance) * (1 - DICE_HOUSE_EDGE);
  $("#diceChanceLabel").textContent = String(chance);
  $("#diceMultiplier").textContent = `x${multiplier.toFixed(2)}`;
  $("#dicePotential").textContent = `${formatNumber(Math.floor(bet * multiplier))} ${coinName}`;
  const zone = $("#diceZone");
  if (diceDirection === "under") {
    $("#diceTarget").textContent = `≤ ${chance}`;
    zone.style.left = "0%";
    zone.style.width = `${chance}%`;
  } else {
    $("#diceTarget").textContent = `> ${100 - chance}`;
    zone.style.left = `${100 - chance}%`;
    zone.style.width = `${chance}%`;
  }
}

function showDiceRoll(roll, success) {
  const marker = $("#diceMarker");
  marker.hidden = false;
  marker.style.left = `${Math.max(0, Math.min(100, roll - 0.5))}%`;
  marker.classList.toggle("hit", success);
  marker.classList.toggle("miss", !success);
  marker.classList.remove("pop");
  void marker.offsetWidth;
  marker.classList.add("pop");
  const face = $("#diceFace");
  face.textContent = roll;
  face.classList.toggle("win-face", success);
  face.classList.toggle("lose-face", !success);
  face.classList.remove("roll");
  void face.offsetWidth;
  face.classList.add("roll");
}

function bindDice() {
  $("#diceChance").addEventListener("input", updateDicePreview);
  $("#diceBet").addEventListener("input", updateDicePreview);
  $$("#diceDirection button").forEach((button) => button.addEventListener("click", () => {
    playSound("click");
    $$("#diceDirection button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    diceDirection = button.dataset.direction;
    updateDicePreview();
  }));
  $("#playDice").addEventListener("click", async () => {
    const button = $("#playDice");
    playSound("roll");
    setBusy(button, true);
    showResult($("#diceResult"), t("dice.roll"), null);
    try {
      const body = await api("/api/games/dice", { method: "POST", body: JSON.stringify({ bet: Number($("#diceBet").value), chance: Number($("#diceChance").value), direction: diceDirection }) });
      const result = body.result;
      showDiceRoll(result.roll, result.success);
      setBalance(result.balance_after);
      showResult($("#diceResult"), result.success ? t("dice.win", { amount: formatNumber(result.win_amount), coin: coinName, roll: result.roll }) : t("dice.lose", { roll: result.roll }), result.success);
      playSound(result.success ? "win" : "lose");
      if (result.success) registerWin("dice", result.multiplier || result.win_amount / Math.max(1, result.bet), result.win_amount); else clearShare("dice");
    } catch (error) {
      showResult($("#diceResult"), error.message, false);
    } finally {
      setBusy(button, false);
    }
  });
  updateDicePreview();
}

function bindPlinko() {
  buildPlinkoPegs();
  updatePlinkoSlots(getPlinkoSlots(selectedPlinkoRisk));
  $$("#plinkoRisk button").forEach((button) => button.addEventListener("click", () => {
    playSound("click");
    $$("#plinkoRisk button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    selectedPlinkoRisk = button.dataset.risk;
    updatePlinkoSlots(getPlinkoSlots(selectedPlinkoRisk));
  }));
  $("#playPlinko").addEventListener("click", playPlinko);
}

function plinkoPegRowCenters() {
  const holder = $("#plinkoPegs");
  // Row offsetTop is relative to the pegs band, which starts below the field top.
  return $$("#plinkoPegs .peg-row").map((row) => holder.offsetTop + row.offsetTop + 4);
}

function animatePlinkoBall(result) {
  const ball = $("#plinkoBall");
  const field = $("#plinkoField");
  const slots = $$("#plinkoSlots div");
  const slotsHolder = $("#plinkoSlots");
  const hitSlot = slots[result.slot_index];
  const fieldWidth = field.clientWidth || 360;
  const fieldHeight = field.clientHeight || 360;
  const slotCenterLeft = hitSlot
    ? slotsHolder.offsetLeft + hitSlot.offsetLeft + hitSlot.offsetWidth / 2
    : fieldWidth * ((result.slot_index + 0.5) / result.slots.length);
  const slotTop = hitSlot ? slotsHolder.offsetTop + hitSlot.offsetTop : fieldHeight - 50;
  const finalLeft = Math.max(14, Math.min(fieldWidth - 14, slotCenterLeft));
  const landTop = Math.max(60, slotTop - 12);
  const rowYs = plinkoPegRowCenters().filter((rowY) => rowY < landTop - 30);
  const margin = 18;

  // Random walk between peg rows that always converges to the winning slot.
  let x = fieldWidth / 2 + (Math.random() * 12 - 6);
  const startX = x;
  const xs = rowYs.map((_, index) => {
    const remaining = rowYs.length - index;
    const step = (finalLeft - x) / remaining;
    const jitter = remaining === 1 ? 0 : (Math.random() - 0.5) * 30;
    x = Math.max(margin, Math.min(fieldWidth - margin, x + step + jitter));
    return x;
  });

  const frames = [{ left: `${startX}px`, top: "14px", transform: "translate(-50%, 0) scale(1)", easing: "cubic-bezier(.5, 0, 1, .5)" }];
  const weights = [];
  const contactFrameIndexes = [];
  const addFrame = (frame, weight) => {
    frames.push(frame);
    weights.push(weight);
  };

  rowYs.forEach((rowY, index) => {
    const contactY = Math.max(24, rowY - 22);
    // Accelerating fall into the peg, slight squash on impact.
    addFrame(
      { left: `${xs[index]}px`, top: `${contactY}px`, transform: "translate(-50%, 0) scale(1.08, .88)", easing: "cubic-bezier(0, .45, .5, 1)" },
      index === 0 ? 1.2 : 1
    );
    contactFrameIndexes.push(frames.length - 1);
    // Short decelerating hop toward the next column.
    const nextX = index + 1 < xs.length ? xs[index + 1] : finalLeft;
    const hopX = xs[index] + (nextX - xs[index]) * 0.35;
    addFrame(
      { left: `${hopX}px`, top: `${contactY - 9}px`, transform: "translate(-50%, 0) scale(.96, 1.06)", easing: "cubic-bezier(.5, 0, 1, .5)" },
      0.55
    );
  });

  // Final fall into the slot, then a damped double bounce.
  addFrame({ left: `${finalLeft}px`, top: `${landTop}px`, transform: "translate(-50%, 0) scale(1.12, .82)", easing: "cubic-bezier(0, .5, .45, 1)" }, 1.25);
  const landFrameIndex = frames.length - 1;
  addFrame({ left: `${finalLeft}px`, top: `${landTop - 15}px`, transform: "translate(-50%, 0) scale(.96, 1.05)", easing: "cubic-bezier(.55, 0, 1, .5)" }, 0.7);
  addFrame({ left: `${finalLeft}px`, top: `${landTop}px`, transform: "translate(-50%, 0) scale(1.06, .9)", easing: "cubic-bezier(0, .5, .5, 1)" }, 0.6);
  addFrame({ left: `${finalLeft}px`, top: `${landTop - 5}px`, transform: "translate(-50%, 0) scale(1)", easing: "cubic-bezier(.5, 0, .5, 1)" }, 0.4);
  addFrame({ left: `${finalLeft}px`, top: `${landTop}px`, transform: "translate(-50%, 0) scale(1)" }, 0.35);

  const totalWeight = weights.reduce((sum, value) => sum + value, 0);
  const offsets = [0];
  let acc = 0;
  weights.forEach((weight) => {
    acc += weight;
    offsets.push(Math.min(1, acc / totalWeight));
  });
  frames.forEach((frame, index) => {
    frame.offset = offsets[index];
  });

  const duration = 2350 + rowYs.length * 85;
  field.classList.remove("dropping");
  void field.offsetWidth;
  field.classList.add("dropping");
  setTimeout(() => field.classList.remove("dropping"), duration);

  haptic("bet");
  contactFrameIndexes.forEach((frameIndex, index) => {
    playTone(470 + index * 26, 0.03, { delay: (offsets[frameIndex] * duration) / 1000, type: "square", volume: 0.02 });
  });
  playTone(700, 0.06, { delay: (offsets[landFrameIndex] * duration) / 1000, type: "triangle", volume: 0.04 });

  ball.animate(frames, { duration, fill: "forwards" });
  return duration;
}

async function playPlinko() {
  const button = $("#playPlinko");
  let unlockDelay = 3000;
  playSound("click");
  setBusy(button, true);
  $$("#plinkoSlots div").forEach((slot) => slot.classList.remove("hit"));
  showResult($("#plinkoResult"), t("plinko.drop"), null);
  try {
    const body = await api("/api/games/plinko", { method: "POST", body: JSON.stringify({ bet: Number($("#plinkoBet").value), risk: selectedPlinkoRisk }) });
    const result = body.result;
    updatePlinkoSlots(result.slots);
    const duration = animatePlinkoBall(result);
    unlockDelay = duration + 80;
    setTimeout(() => {
      $$("#plinkoSlots div")[result.slot_index]?.classList.add("hit");
      setBalance(result.balance_after);
      showResult($("#plinkoResult"), t("plinko.result", { risk: t(`risk.${result.risk}`), multiplier: result.multiplier, amount: formatNumber(result.win_amount), coin: coinName }), result.win_amount > result.bet);
      playSound("slot");
      playSound(result.success ? "win" : "lose");
      if (result.win_amount > result.bet) registerWin("plinko", result.multiplier, result.win_amount); else clearShare("plinko");
    }, Math.max(300, duration - 50));
  } catch (error) {
    unlockDelay = 0;
    showResult($("#plinkoResult"), error.message, false);
  } finally {
    setTimeout(() => setBusy(button, false), unlockDelay);
  }
}

function getPlinkoSlots(risk) {
  return plinkoRisks?.[risk]?.multipliers || config.plinkoSlots || [];
}

function plinkoSlotTone(multiplier) {
  const value = Number(multiplier);
  if (value >= 5) return "tone-hot";
  if (value >= 1.3) return "tone-good";
  if (value >= 0.9) return "tone-even";
  return "tone-cold";
}

function updatePlinkoSlots(slots) {
  $("#plinkoSlots").innerHTML = slots.map((slot) => `<div class="${plinkoSlotTone(slot)}">x${slot}</div>`).join("");
}

function buildPlinkoPegs() {
  const holder = $("#plinkoPegs");
  holder.innerHTML = "";
  [3, 4, 5, 6, 7, 6, 5, 4].forEach((count, index) => {
    const row = document.createElement("div");
    row.className = "peg-row";
    row.style.setProperty("--row", index);
    row.style.setProperty("--count", count);
    for (let i = 0; i < count; i += 1) row.appendChild(document.createElement("span"));
    holder.appendChild(row);
  });
}

function bindCrash() {
  $("#startCrash").addEventListener("click", async () => {
    setBusy($("#startCrash"), true);
    showResult($("#crashResult"), t("crash.adding"), null);
    playSound("bet");
    try {
      const body = await api("/api/games/crash/bet", { method: "POST", body: JSON.stringify({ bet: Number($("#crashBet").value) }) });
      hasCrashBet = Boolean(body.result.player);
      setBalance(body.result.balance_after);
      renderCrashState(body.result);
      showResult($("#crashResult"), t("crash.accepted"), true);
    } catch (error) {
      showResult($("#crashResult"), error.message, false);
    } finally {
      setBusy($("#startCrash"), false);
    }
  });
  $("#cashoutCrash").addEventListener("click", async () => {
    $("#cashoutCrash").disabled = true;
    playSound("click");
    try {
      const body = await api("/api/games/crash/cashout", { method: "POST" });
      renderCrashState(body.result);
      if (body.result.cashout) {
        setBalance(body.result.cashout.balance_after);
        showResult($("#crashResult"), t("crash.cashed", { amount: formatNumber(body.result.cashout.payout), coin: coinName, multiplier: body.result.cashout.multiplier.toFixed(2) }), true);
        playSound("win");
        registerWin("crash", body.result.cashout.multiplier, body.result.cashout.payout);
      }
    } catch (error) {
      showResult($("#crashResult"), error.message, false);
    }
  });
}

let crashPollGeneration = 0;

function startCrashPolling(delay = 0) {
  if (!initData) return;
  stopCrashPolling();
  const gen = crashPollGeneration;
  crashPollTimer = setTimeout(() => pollCrashState(gen), delay);
}

function stopCrashPolling() {
  crashPollGeneration += 1;
  if (crashPollTimer) clearTimeout(crashPollTimer);
  crashPollTimer = null;
}

function scheduleCrashPolling(gen, delay = 1000) {
  if (gen !== crashPollGeneration || activeView !== "crash" || !initData) return;
  crashPollTimer = setTimeout(() => pollCrashState(gen), delay);
}

async function pollCrashState(gen) {
  if (gen !== crashPollGeneration) return;
  if (!initData || activeView !== "crash") return;
  const waitMs = Math.max(0, crashRetryUntil - Date.now());
  if (waitMs > 0) {
    scheduleCrashPolling(gen, waitMs);
    return;
  }
  try {
    const body = await api("/api/games/crash/state");
    if (gen !== crashPollGeneration) return;
    renderCrashState(body.result);
    scheduleCrashPolling(gen, 1000);
  } catch (error) {
    if (gen !== crashPollGeneration) return;
    if (error.status === 429 && error.retryAfter) {
      crashRetryUntil = Date.now() + Math.ceil(error.retryAfter * 1000);
      scheduleCrashPolling(gen, Math.ceil(error.retryAfter * 1000));
      return;
    }
    showResult($("#crashResult"), error.message, false);
    scheduleCrashPolling(gen, 2000);
  }
}

function renderCrashState(state) {
  const round = state.round;
  const player = state.player;
  hasCrashBet = Boolean(player);
  crashSync = {
    at: performance.now(),
    status: state.status,
    multiplier: Number(state.multiplier || 1),
    seconds: Number(state.seconds_to_start || 0),
  };
  $("#crashMultiplier").textContent = `x${Number(state.multiplier || 1).toFixed(2)}`;
  updateCrashPath(Number(state.multiplier || 1));
  $("#crashStage").classList.toggle("crashed", state.status === "crashed");
  $("#crashStage").classList.toggle("running", state.status === "running");
  setRoundProgress("crashProgressFill", state.status, Number(state.seconds_to_start || 0), 10);
  $("#crashStatus").textContent = { idle: t("crash.waiting"), countdown: t("crash.accepting"), running: t("crash.running"), crashed: t("crash.crashedStatus") }[state.status] || state.status;
  $("#crashCountdown").textContent = state.status === "countdown" ? `${Number(state.seconds_to_start || 0).toFixed(1)}s` : "-";
  $("#crashPlayers").textContent = round?.players_count || 0;
  $("#crashTotalBet").textContent = `${formatNumber(round?.total_bet || 0)} ${coinName}`;
  $("#startCrash").disabled = state.status === "running" || state.status === "crashed" || hasCrashBet;
  $("#cashoutCrash").disabled = !(state.status === "running" && player && !player.cashed_out);
  if (state.status === "crashed" && round?.crash_at) {
    showResult($("#crashResult"), t("crash.crashed", { multiplier: Number(round.crash_at).toFixed(2) }), false);
    if (player && !player.cashed_out) clearShare("crash");
    if (player && player.balance_after !== null && player.balance_after !== undefined) setBalance(player.balance_after);
    if (round?.round_id && lastCrashSoundRoundId !== round.round_id) {
      lastCrashSoundRoundId = round.round_id;
      playSound(player?.cashed_out ? "slot" : "crash");
    }
  }
  renderCrashLeaderboard(state.leaderboard || []);
  renderCrashHistory(state.round_history || []);
}

function renderCrashLeaderboard(rows) {
  const list = $("#crashLeaderboard");
  list.innerHTML = rows.length ? rows.map((row) => `<li><span>${escapeHtml(row.name)}</span><strong>${formatNumber(row.bet)} ${coinName}</strong><em>${row.cashed_out ? `x${Number(row.cashout_multiplier).toFixed(2)}` : t("crash.inGame")}</em></li>`).join("") : `<li class="empty">${t("crash.noBets")}</li>`;
}

function renderCrashHistory(rows) {
  lastCrashHistory = rows;
  $("#crashRoundHistory").innerHTML = rows.length ? rows.slice(0, 10).map((row) => {
    const crashAt = Number(row.crash_at || 1);
    const tone = crashAt >= 5 ? "hot" : crashAt >= 2 ? "good" : "cold";
    return `<button type="button" class="round-chip ${tone}">x${crashAt.toFixed(2)}</button>`;
  }).join("") : `<span class="round-empty">${t("crash.noHistory")}</span>`;
}

function updateCrashPath(multiplier) {
  const lift = Math.min(120, 18 + multiplier * 18);
  $("#crashPath").setAttribute("d", `M0 142 C 80 140, 150 ${150 - lift * 0.42}, 320 ${154 - lift}`);
  const stage = $("#crashStage");
  const dot = $("#crashDot");
  if (stage && dot) {
    dot.style.left = `${stage.clientWidth - 10}px`;
    dot.style.top = `${((154 - lift) / 160) * stage.clientHeight}px`;
  }
}

function setRoundProgress(fillId, status, secondsLeft, totalSeconds) {
  const fill = document.getElementById(fillId);
  if (!fill) return;
  if (status !== "countdown") {
    fill.style.width = status === "running" ? "100%" : "0%";
    return;
  }
  const pct = Math.max(0, Math.min(100, (1 - secondsLeft / totalSeconds) * 100));
  fill.style.width = `${pct}%`;
}

// --- Smooth live UI: interpolate crash multiplier and countdowns between polls ---
let crashSync = null;      // { at, status, multiplier, seconds }
let rouletteSync = null;   // { at, status, seconds }
let bonusSync = null;      // { available, availableAt }
let bonusHoldUntil = 0;
let lastLiveCrashText = "";
let lastLiveCrashCountdown = "";
let lastLiveRouletteCountdown = "";
let lastLiveBonusText = "";

function crashElapsedFromMultiplier(multiplier) {
  if (multiplier <= 1) return 0;
  // Inverse of m = 1 + 0.06e + 0.006e^2
  return (-0.06 + Math.sqrt(0.0036 + 0.024 * (multiplier - 1))) / 0.012;
}

function crashMultiplierAt(elapsed) {
  return 1 + elapsed * 0.06 + elapsed * elapsed * 0.006;
}

function updateLiveGameUi() {
  const now = performance.now();
  if (activeView === "crash" && crashSync) {
    const dt = (now - crashSync.at) / 1000;
    if (crashSync.status === "countdown") {
      const left = Math.max(0, crashSync.seconds - dt);
      const text = `${left.toFixed(1)}s`;
      setRoundProgress("crashProgressFill", "countdown", left, 10);
      if (text !== lastLiveCrashCountdown) {
        lastLiveCrashCountdown = text;
        $("#crashCountdown").textContent = text;
      }
    } else if (crashSync.status === "running") {
      const estimated = crashMultiplierAt(crashElapsedFromMultiplier(crashSync.multiplier) + dt);
      const text = `x${estimated.toFixed(2)}`;
      if (text !== lastLiveCrashText) {
        lastLiveCrashText = text;
        $("#crashMultiplier").textContent = text;
        updateCrashPath(estimated);
      }
    }
  }
  if (activeView === "roulette" && rouletteSync && rouletteSync.status === "countdown") {
    const left = Math.max(0, rouletteSync.seconds - (now - rouletteSync.at) / 1000);
    const text = `${left.toFixed(1)}s`;
    setRoundProgress("rouletteProgressFill", "countdown", left, 10);
    if (text !== lastLiveRouletteCountdown) {
      lastLiveRouletteCountdown = text;
      $("#rouletteCountdown").textContent = text;
    }
  }
  updateBonusCountdownUi();
  requestAnimationFrame(updateLiveGameUi);
}

function updateBonusCountdownUi() {
  if (!bonusSync || bonusSync.available) return;
  if (Date.now() < bonusHoldUntil) return;
  const status = $("#dailyBonusStatus");
  if (!status) return;
  const leftMs = bonusSync.availableAt - Date.now();
  if (leftMs <= 0) {
    bonusSync.available = true;
    status.classList.remove("win", "lose");
    status.textContent = t("bonus.ready");
    $("#claimDailyBonus").disabled = false;
    $(".bonus-action")?.classList.add("bonus-ready");
    return;
  }
  const text = t("bonus.wait", { time: fmtTime(leftMs / 1000) });
  if (text !== lastLiveBonusText) {
    lastLiveBonusText = text;
    status.classList.remove("win", "lose");
    status.textContent = text;
  }
}

const ROULETTE_RANGE_INFO = {
  low: { label: "1–18", multiplier: 2 },
  high: { label: "19–36", multiplier: 2 },
  first12: { label: "1–12", multiplier: 3 },
  second12: { label: "13–24", multiplier: 3 },
  third12: { label: "25–36", multiplier: 3 },
};

function buildRouletteNumberGrid() {
  const grid = $("#rouletteNumberGrid");
  if (!grid || grid.dataset.ready === "1") return;
  grid.dataset.ready = "1";
  const cells = [];
  for (let number = 0; number <= 36; number += 1) {
    cells.push(`<button type="button" class="num-cell ${rouletteCellTone(number)}${number === 0 ? " zero" : ""}" data-number="${number}">${number}</button>`);
  }
  grid.innerHTML = cells.join("");
  $$("#rouletteNumberGrid .num-cell").forEach((cell) => {
    cell.addEventListener("click", () => {
      playSound("click");
      rouletteNumber = Number(cell.dataset.number);
      $$("#rouletteNumberGrid .num-cell").forEach((item) => item.classList.toggle("active", item === cell));
      renderRouletteBetControls();
    });
  });
  grid.querySelector(`[data-number="${rouletteNumber}"]`)?.classList.add("active");
}

function bindRoulette() {
  buildRouletteWheel();
  buildRouletteNumberGrid();
  $("#rouletteBet").addEventListener("input", updateRouletteSummary);
  $$("#rouletteBetType button").forEach((button) => button.addEventListener("click", () => {
    playSound("click");
    rouletteBetType = button.dataset.type;
    $$("#rouletteBetType button").forEach((item) => item.classList.toggle("active", item === button));
    renderRouletteBetControls();
  }));
  $$("#rouletteColorChoices button").forEach((button) => button.addEventListener("click", () => {
    playSound("click");
    rouletteColor = button.dataset.color;
    $$("#rouletteColorChoices button").forEach((item) => item.classList.toggle("active", item === button));
    renderRouletteBetControls();
  }));
  $$("#rouletteRangePane [data-range]").forEach((button) => button.addEventListener("click", () => {
    playSound("click");
    rouletteRange = button.dataset.range;
    $$("#rouletteRangePane [data-range]").forEach((item) => item.classList.toggle("active", item === button));
    renderRouletteBetControls();
  }));
  $("#placeRoulette").addEventListener("click", async () => {
    setBusy($("#placeRoulette"), true);
    playSound("bet");
    try {
      const body = await api("/api/games/roulette/bet", { method: "POST", body: JSON.stringify(rouletteBetPayload()) });
      hasRouletteBet = Boolean(body.result.player);
      setBalance(body.result.balance_after);
      renderRouletteState(body.result);
      showResult($("#rouletteResult"), `${t("roulette.spin")} ${t("roulette.selection", { selection: rouletteSelectionLabel(body.result.player) })}`, true);
    } catch (error) {
      showResult($("#rouletteResult"), error.message, false);
    } finally {
      setBusy($("#placeRoulette"), false);
    }
  });
  renderRouletteBetControls();
}

function rouletteBetPayload() {
  const body = { bet: Number($("#rouletteBet").value), bet_type: rouletteBetType };
  if (rouletteBetType === "number") body.number = rouletteNumber;
  if (rouletteBetType === "color") body.color = rouletteColor;
  if (rouletteBetType === "range") body.range = rouletteRange;
  return body;
}

function currentRouletteMultiplier() {
  if (rouletteBetType === "number") return 36;
  if (rouletteBetType === "color") return 2;
  return ROULETTE_RANGE_INFO[rouletteRange]?.multiplier || 2;
}

function currentRouletteSelectionText() {
  if (rouletteBetType === "number") return `#${rouletteNumber}`;
  if (rouletteBetType === "color") return t(rouletteColor === "red" ? "roulette.red" : "roulette.black");
  return ROULETTE_RANGE_INFO[rouletteRange]?.label || rouletteRange;
}

function updateRouletteSummary() {
  const multiplier = currentRouletteMultiplier();
  const selection = $("#rouletteSelectionText");
  if (selection) selection.textContent = `${currentRouletteSelectionText()} · x${multiplier}`;
  const bet = Math.max(0, Number($("#rouletteBet").value) || 0);
  $("#roulettePotential").textContent = `${formatNumber(bet * multiplier)} ${coinName}`;
}

function renderRouletteBetControls() {
  $("#rouletteNumberPane").hidden = rouletteBetType !== "number";
  $("#rouletteColorPane").hidden = rouletteBetType !== "color";
  $("#rouletteRangePane").hidden = rouletteBetType !== "range";
  highlightRouletteCells(null, rouletteBetType === "number" ? rouletteNumber : null);
  updateRouletteSummary();
}

function buildRouletteWheel() {
  const track = $("#rouletteTrack");
  if (!track || track.dataset.ready === "1") return;
  track.dataset.ready = "1";
  const step = 360 / rouletteOrder.length;
  rouletteOrder.forEach((number, index) => {
    const cell = document.createElement("span");
    const angle = index * step;
    cell.className = `roulette-cell ${rouletteCellTone(number)}`;
    cell.dataset.number = String(number);
    cell.style.setProperty("--angle", `${angle}deg`);
    cell.style.setProperty("--reverse-angle", `${-angle}deg`);
    cell.textContent = number;
    track.appendChild(cell);
  });
  highlightRouletteCells(null, rouletteNumber);
}

function rouletteCellTone(number) {
  if (number === 0) return "green";
  return rouletteReds.has(number) ? "red" : "black";
}

function highlightRouletteCells(hitNumber, pickNumber) {
  $$(".roulette-cell").forEach((cell) => {
    const value = Number(cell.dataset.number);
    cell.classList.toggle("hit", hitNumber !== null && value === Number(hitNumber));
    cell.classList.toggle("pick", hitNumber === null && pickNumber !== null && pickNumber !== undefined && value === Number(pickNumber));
  });
}

function spinRouletteTo(number) {
  const track = $("#rouletteTrack");
  const ball = $("#rouletteBall");
  const index = rouletteOrder.indexOf(Number(number));
  if (!track || !ball || index < 0) return 0;

  const step = 360 / rouletteOrder.length;
  const sectorAngle = index * step;
  const currentTrackNorm = ((rouletteTrackRotation % 360) + 360) % 360;
  const targetTrackNorm = (360 - sectorAngle) % 360;
  const duration = 5000 + Math.floor(Math.random() * 2501);
  const extraTurns = 5 + Math.floor(Math.random() * 3);
  const delta = (targetTrackNorm - currentTrackNorm + 360) % 360;
  const nextTrackRotation = rouletteTrackRotation + extraTurns * 360 + delta;
  const nextBallRotation = rouletteBallRotation - (extraTurns + 2) * 360 - delta - 64;

  track.animate(
    [{ transform: `rotate(${rouletteTrackRotation}deg)` }, { transform: `rotate(${nextTrackRotation}deg)` }],
    { duration, easing: "cubic-bezier(.12,.78,.16,1)", fill: "forwards" }
  );
  ball.animate(
    [{ transform: `rotate(${rouletteBallRotation}deg) translateY(calc(var(--wheel-size) * -.475))` }, { transform: `rotate(${nextBallRotation}deg) translateY(calc(var(--wheel-size) * -.475))` }],
    { duration, easing: "cubic-bezier(.08,.72,.18,1)", fill: "forwards" }
  );
  rouletteTrackRotation = nextTrackRotation;
  rouletteBallRotation = nextBallRotation;
  playSound("spin", { duration });
  return duration;
}

let roulettePollGeneration = 0;

function startRoulettePolling(delay = 0) {
  if (!initData) return;
  stopRoulettePolling();
  const gen = roulettePollGeneration;
  roulettePollTimer = setTimeout(() => pollRouletteState(gen), delay);
}

function stopRoulettePolling() {
  roulettePollGeneration += 1;
  if (roulettePollTimer) clearTimeout(roulettePollTimer);
  roulettePollTimer = null;
}

function scheduleRoulettePolling(gen, delay = 1200) {
  if (gen !== roulettePollGeneration || activeView !== "roulette" || !initData) return;
  roulettePollTimer = setTimeout(() => pollRouletteState(gen), delay);
}

async function pollRouletteState(gen) {
  if (gen !== roulettePollGeneration) return;
  if (!initData || activeView !== "roulette") return;
  const waitMs = Math.max(0, rouletteRetryUntil - Date.now());
  if (waitMs > 0) {
    scheduleRoulettePolling(gen, waitMs);
    return;
  }
  try {
    const body = await api("/api/games/roulette/state");
    if (gen !== roulettePollGeneration) return;
    renderRouletteState(body.result);
    scheduleRoulettePolling(gen, 1200);
  } catch (error) {
    if (gen !== roulettePollGeneration) return;
    if (error.status === 429 && error.retryAfter) {
      rouletteRetryUntil = Date.now() + Math.ceil(error.retryAfter * 1000);
      scheduleRoulettePolling(gen, Math.ceil(error.retryAfter * 1000));
      return;
    }
    showResult($("#rouletteResult"), error.message, false);
    scheduleRoulettePolling(gen, 2500);
  }
}

function renderRouletteState(state) {
  const round = state.round;
  const player = state.player;
  hasRouletteBet = Boolean(player);
  rouletteSync = {
    at: performance.now(),
    status: state.status,
    seconds: Number(state.seconds_to_start || 0),
  };
  $("#rouletteStatus").textContent = { idle: t("crash.waiting"), countdown: t("crash.accepting"), resolved: t("roulette.resultStatus") }[state.status] || state.status;
  $("#rouletteCountdown").textContent = state.status === "countdown" ? `${Number(state.seconds_to_start || 0).toFixed(1)}s` : "-";
  setRoundProgress("rouletteProgressFill", state.status, Number(state.seconds_to_start || 0), 10);
  $("#roulettePlayers").textContent = round?.players_count || 0;
  $("#rouletteTotalBet").textContent = `${formatNumber(round?.total_bet || 0)} ${coinName}`;
  $("#placeRoulette").disabled = state.status !== "idle" && (state.status !== "countdown" || hasRouletteBet);
  if (round?.winning_number !== null && round?.winning_number !== undefined) {
    const isNewResolvedRound = lastRenderedRouletteRoundId !== round.round_id;
    if (isNewResolvedRound) {
      lastRenderedRouletteRoundId = round.round_id;
      const spinDuration = spinRouletteTo(round.winning_number);
      const revealDelay = Math.max(500, spinDuration - 80);
      rouletteAnimatingRoundId = round.round_id;
      rouletteAnimatingUntil = Date.now() + revealDelay;
      showResult($("#rouletteResult"), t("roulette.rolling"), null);
      setTimeout(() => {
        rouletteAnimatingRoundId = null;
        rouletteAnimatingUntil = 0;
        const hub = $("#rouletteNumber");
        hub.textContent = round.winning_number;
        hub.className = `hub-${rouletteCellTone(Number(round.winning_number))}`;
        hub.classList.remove("hub-pop");
        void hub.offsetWidth;
        hub.classList.add("hub-pop");
        highlightRouletteCells(round.winning_number, null);
        playSound(player ? (player.payout > 0 ? "win" : "lose") : "slot");
        if (player) {
          showResult($("#rouletteResult"), rouletteResultText(round.winning_number, player), player.payout > 0);
          if (player.payout > 0) registerWin("roulette", player.payout / Math.max(1, player.bet), player.payout); else clearShare("roulette");
        }
      }, revealDelay);
    } else if (rouletteAnimatingRoundId === round.round_id && Date.now() < rouletteAnimatingUntil) {
      showResult($("#rouletteResult"), t("roulette.rolling"), null);
    } else {
      const hub = $("#rouletteNumber");
      hub.textContent = round.winning_number;
      hub.className = `hub-${rouletteCellTone(Number(round.winning_number))}`;
      highlightRouletteCells(round.winning_number, null);
    }
    if (player && player.balance_after !== null && player.balance_after !== undefined) setBalance(player.balance_after);
    if (player && !isNewResolvedRound && !(rouletteAnimatingRoundId === round.round_id && Date.now() < rouletteAnimatingUntil)) {
      showResult($("#rouletteResult"), rouletteResultText(round.winning_number, player), player.payout > 0);
    }
  } else if (state.status === "idle" || state.status === "countdown") {
    const hub = $("#rouletteNumber");
    hub.textContent = "?";
    hub.className = "";
    highlightRouletteCells(null, player?.number ?? rouletteNumber);
  }
  renderRouletteHistory(state.history || []);
  renderRouletteLeaderboard(state.leaderboard || []);
}

function rouletteResultText(number, player) {
  return player.payout > 0
    ? `${t("roulette.win", { number, amount: formatNumber(player.payout), coin: coinName })} · ${rouletteSelectionLabel(player)}`
    : `${t("roulette.lose", { number })} · ${rouletteSelectionLabel(player)}`;
}

function renderRouletteHistory(rows) {
  lastRouletteHistory = rows;
  $("#rouletteHistory").innerHTML = rows.length ? rows.slice(0, 12).map((row) => {
    const number = Number(row.winning_number);
    return `<button type="button" class="round-chip roulette-chip ${rouletteCellTone(number)}">${number}</button>`;
  }).join("") : `<span class="round-empty">${t("crash.noHistory")}</span>`;
}

function renderRouletteLeaderboard(rows) {
  lastRouletteLeaders = rows;
  $("#rouletteLeaderboard").innerHTML = rows.length ? rows.map((row) => `<li><span>${escapeHtml(row.name)}</span><strong>${formatNumber(row.bet)} ${coinName}</strong><em>${escapeHtml(rouletteSelectionLabel(row))}</em></li>`).join("") : `<li class="empty">${t("crash.noBets")}</li>`;
}

function rouletteSelectionLabel(player) {
  if (!player) return "";
  if (player.bet_type === "number") return `#${player.number}`;
  if (player.bet_type === "color") return player.color === "red" ? t("roulette.red") : t("roulette.black");
  return player.selection || player.range_key || "";
}

function bindBonusInvite() {
  $("#claimDailyBonus").addEventListener("click", async () => {
    setBusy($("#claimDailyBonus"), true);
    try {
      const body = await api("/api/bonus/daily", { method: "POST" });
      renderBonus(body.bonus);
      if (body.user) setBalance(body.user.balance);
      if (body.bonus.claimed) playSound("win");
      bonusHoldUntil = Date.now() + 4000;
      showResult($("#dailyBonusStatus"), body.bonus.claimed ? t("bonus.claimed", { amount: formatNumber(body.bonus.amount), coin: coinName }) : t("bonus.wait", { time: fmtTime(body.bonus.seconds_left) }), body.bonus.claimed);
    } catch (error) {
      showResult($("#dailyBonusStatus"), error.message, false);
    } finally {
      setBusy($("#claimDailyBonus"), false);
    }
  });
  $("#copyInvite").addEventListener("click", async () => {
    const value = $("#inviteLink").value;
    try {
      await navigator.clipboard.writeText(value);
      showResult($("#dailyBonusStatus"), t("invite.copied"), true);
    } catch (_) {
      $("#inviteLink").select();
    }
  });
  $("#shareInvite")?.addEventListener("click", shareInviteLink);
  $("#shareProfileInvite")?.addEventListener("click", shareInviteLink);
}

function shareInviteLink() {
  const link = currentInviteLink || $("#inviteLink").value;
  if (!link) return;
  playSound("click");
  const text = t("share.invite");
  const url = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`;
  if (tg?.openTelegramLink) tg.openTelegramLink(url); else window.open(url, "_blank");
}

let wheelSync = null;
let wheelRotation = 0;
let wheelSpinning = false;

function buildWheelDisc(prizes) {
  const disc = $("#wheelDisc");
  if (!disc || disc.childElementCount === prizes.length) return;
  const step = 360 / prizes.length;
  disc.innerHTML = prizes.map((amount, index) => `
    <span style="transform: rotate(${index * step + step / 2}deg) translate(-50%, -78px)">${formatNumber(amount)}</span>
  `).join("");
}

function renderWheel(wheel) {
  if (!wheel || wheelSpinning) return;
  wheelSync = wheel;
  buildWheelDisc(wheel.prizes || []);
  const status = $("#wheelStatus");
  status.classList.remove("win", "lose");
  status.textContent = wheel.available ? t("wheel.ready") : t("wheel.wait", { time: fmtTime(wheel.seconds_left) });
  $("#wheelSpin").disabled = !wheel.available;
}

async function spinWheel() {
  if (wheelSpinning) return;
  const button = $("#wheelSpin");
  wheelSpinning = true;
  setBusy(button, true);
  try {
    const body = await api("/api/wheel/spin", { method: "POST" });
    const wheel = body.wheel;
    if (!wheel.claimed) {
      wheelSpinning = false;
      setBusy(button, false);
      renderWheel(wheel);
      return;
    }
    playSound("spin", { duration: 3600 });
    const disc = $("#wheelDisc");
    const step = wheel.prizes?.length ? 360 / wheel.prizes.length : 45;
    const target = wheel.prize_index * step + step / 2;
    wheelRotation += 4 * 360 + ((360 - target) - (wheelRotation % 360) + 360) % 360;
    disc.style.transform = `rotate(${wheelRotation}deg)`;
    setTimeout(() => {
      playSound("win");
      if (body.user) setBalance(body.user.balance);
      showResult($("#wheelStatus"), t("wheel.won", { amount: formatNumber(wheel.amount), coin: coinName }), true);
      button.disabled = true;
      wheelSpinning = false;
      setBusy(button, false);
      wheelSync = { ...wheel, claimed: false };
    }, 3700);
  } catch (error) {
    wheelSpinning = false;
    setBusy(button, false);
    showResult($("#wheelStatus"), error.message, false);
  }
}

function bindWheel() {
  $("#wheelSpin")?.addEventListener("click", spinWheel);
}

function renderBonus(bonus) {
  if (!bonus) return;
  bonusSync = {
    available: Boolean(bonus.available),
    availableAt: Date.now() + Number(bonus.seconds_left || 0) * 1000,
  };
  $("#dailyBonusAmount").textContent = `${formatNumber(bonus.amount)} ${coinName}`;
  $("#dailyBonusStatus").textContent = bonus.available ? t("bonus.ready") : t("bonus.wait", { time: fmtTime(bonus.seconds_left) });
  $("#claimDailyBonus").disabled = !bonus.available;
  $(".bonus-action")?.classList.toggle("bonus-ready", Boolean(bonus.available));
}

async function loadShopPackages() {
  try {
    const body = await api("/api/shop/packages");
    renderShopPackages(body.packages);
  } catch (_) {}
}

function renderShopPackages(packages, remember = true) {
  if (remember) lastShopPackages = packages || [];
  $("#shopGrid").innerHTML = packages.map((pkg) => `
    <button type="button" class="shop-card ${escapeHtml(pkg.category || "utility")}" data-kind="${escapeHtml(pkg.kind)}">
      <strong>${escapeHtml(shopTitle(pkg))}</strong>
      <p>${escapeHtml(shopDescription(pkg))}</p>
      <small>${t("shop.buy", { stars: pkg.stars })}</small>
    </button>
  `).join("");
  $$("#shopGrid .shop-card").forEach((button) => button.addEventListener("click", () => buyShopItem(button.dataset.kind)));
}

function shopTitle(pkg) {
  const key = `shop.item.${pkg.kind}.title`;
  const translated = t(key);
  if (translated !== key) return translated;
  return pkg.title || pkg.kind;
}

function shopDescription(pkg) {
  const key = `shop.item.${pkg.kind}.desc`;
  const translated = t(key);
  if (translated !== key) return translated;
  return pkg.description || "";
}

async function buyShopItem(kind) {
  try {
    playSound("click");
    const body = await api("/api/shop/invoice", { method: "POST", body: JSON.stringify({ kind }) });
    if (tg?.openInvoice) {
      tg.openInvoice(body.invoice.invoice_link, () => loadMe());
    } else {
      window.open(body.invoice.invoice_link, "_blank");
    }
    showResult($("#shopResult"), kind === "daily_bonus_renew" ? t("shop.renewed") : t("shop.invoiceOpened"), true);
  } catch (error) {
    showResult($("#shopResult"), error.message, false);
  }
}

let leadersPeriod = "all";

async function loadLeaderboard() {
  if (!initData) return;
  try {
    const body = await api(`/api/leaderboard?period=${leadersPeriod}`);
    const medals = ["🥇", "🥈", "🥉"];
    $("#leadersList").innerHTML = body.leaders.map((user, index) => {
      const name = user.username ? `@${user.username}` : user.first_name || user.telegram_id;
      const place = index < 3 && leadersPeriod === "week" ? medals[index] : `${index + 1}.`;
      const value = leadersPeriod === "week"
        ? `${formatNumber(user.weekly_won)} ${coinName}`
        : `${formatNumber(user.balance)} ${coinName}`;
      return `<li><span>${place} ${escapeHtml(name)}</span><strong>${value}</strong></li>`;
    }).join("") || `<li><span>${t("leaders.empty")}</span></li>`;
  } catch (_) {}
}

function bindLeaderboard() {
  $("#refreshLeaders").addEventListener("click", loadLeaderboard);
  $$("#leadersPeriod button").forEach((button) => button.addEventListener("click", () => {
    playSound("click");
    leadersPeriod = button.dataset.period;
    $$("#leadersPeriod button").forEach((item) => item.classList.toggle("active", item === button));
    $("#leadersWeekHint").hidden = leadersPeriod !== "week";
    loadLeaderboard();
  }));
}

const HISTORY_PAGE_SIZE = 60;
let historyOffset = 0;

async function loadHistory(append = false) {
  if (!initData) return;
  if (!append) historyOffset = 0;
  try {
    const body = await api(`/api/history?limit=${HISTORY_PAGE_SIZE}&offset=${historyOffset}`);
    const rows = body.history || [];
    historyOffset += rows.length;
    renderHistory(append ? lastHistory.concat(rows) : rows);
    const more = $("#historyMore");
    if (more) more.hidden = !body.has_more;
  } catch (error) {
    $("#historyList").innerHTML = `<li class="history-item lose"><span><strong>${escapeHtml(error.message)}</strong></span></li>`;
  }
}

function renderHistory(rows) {
  lastHistory = rows || [];
  const list = $("#historyList");
  if (!list) return;
  if (!lastHistory.length) {
    list.innerHTML = `<li class="history-item empty"><span><strong>${t("history.empty")}</strong></span></li>`;
    return;
  }
  list.innerHTML = lastHistory.map((row) => {
    const isGame = row.type === "game";
    const tone = isGame ? row.outcome : row.outcome === "credit" ? "win" : "lose";
    const title = isGame ? gameTitle(row.kind) : balanceEventTitle(row.kind);
    const when = formatDateTime(row.created_at);
    const details = isGame
      ? `${t("history.bet")} ${formatNumber(row.bet)} / ${t("history.payout")} ${formatNumber(row.win_amount)}`
      : `${Number(row.amount || 0) >= 0 ? "+" : ""}${formatNumber(row.amount)} ${coinName}`;
    const balance = `${t("history.after")} ${formatNumber(row.balance_after)} ${coinName}`;
    return `
      <li class="history-item ${escapeHtml(tone)}">
        <span><strong>${escapeHtml(title)}</strong><small>${escapeHtml(when)} · ${escapeHtml(balance)}</small></span>
        <em>${escapeHtml(details)}</em>
      </li>
    `;
  }).join("");
}

function bindHistory() {
  $("#refreshHistory").addEventListener("click", () => loadHistory(false));
  $("#historyMore")?.addEventListener("click", () => loadHistory(true));
}

async function loadRetention() {
  if (!initData) return;
  try {
    const body = await api("/api/retention");
    renderRetention(body.retention);
  } catch (error) {
    showResult($("#retentionResult"), error.message, false);
  }
}

function renderRetention(retention) {
  lastRetention = retention || lastRetention;
  if (!lastRetention) return;
  applyCosmeticState(lastRetention.active_cosmetic);
  renderRetentionSummary(lastRetention);
  renderSeasonTrack(lastRetention);
  renderQuests(lastRetention);
  renderAchievements(lastRetention);
  renderCosmetics(lastRetention);
}

function progressBar(progress, target) {
  const pct = Math.max(0, Math.min(100, target > 0 ? Math.round((Number(progress) / Number(target)) * 100) : 0));
  return `<div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>`;
}

function renderRetentionSummary(retention) {
  const summary = $("#retentionSummary");
  if (!summary) return;
  const season = retention.season || {};
  const level = Number(season.level || 1);
  const xp = Number(season.xp || 0);
  const levelBase = (level - 1) * 250;
  const nextLevelXp = Math.max(levelBase + 1, Number(season.next_level_xp || levelBase + 250));
  const intoLevel = Math.max(0, xp - levelBase);
  const needForLevel = Math.max(1, nextLevelXp - levelBase);
  summary.innerHTML = [
    [t("retention.streak"), `${formatNumber(retention.streak?.current)} / best ${formatNumber(retention.streak?.best)}`, ""],
    [t("retention.season"), `Lv ${formatNumber(level)} · ${formatNumber(Math.min(intoLevel, needForLevel))}/${formatNumber(needForLevel)} XP`, progressBar(intoLevel, needForLevel)],
    [t("retention.premium"), retention.premium?.active ? formatDateTime(retention.premium.until) : "off", ""],
    ["Season pass", season.pass_active ? formatDateTime(season.pass_until) : "off", ""],
  ].map(([label, value, extra]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>${extra}</div>`).join("");
}

function renderSeasonTrack(retention) {
  const holder = $("#seasonPanel");
  if (!holder) return;
  const season = retention.season || {};
  const track = season.track || [];
  if (!track.length) {
    holder.innerHTML = "";
    return;
  }
  const passActive = Boolean(season.pass_active);
  const currentLevel = Number(season.level || 1);
  const cells = track.map((row) => {
    const freeReady = row.unlocked && !row.free.claimed;
    const premiumReady = row.unlocked && passActive && !row.premium.claimed;
    const cellState = row.level === currentLevel ? "current" : row.unlocked ? "unlocked" : "";
    return `
      <div class="season-cell ${cellState}">
        <strong>Lv ${row.level}</strong>
        <button type="button" class="season-claim ${row.free.claimed ? "claimed" : freeReady ? "ready" : "locked"}"
          data-season-level="${row.level}" data-season-tier="free" ${freeReady ? "" : "disabled"}>
          ${row.free.claimed ? "✓" : `+${formatNumber(row.free.reward)}`}
        </button>
        <button type="button" class="season-claim premium ${row.premium.claimed ? "claimed" : premiumReady ? "ready" : "locked"}"
          data-season-level="${row.level}" data-season-tier="premium" ${premiumReady ? "" : "disabled"}>
          ${row.premium.claimed ? "✓" : `★ +${formatNumber(row.premium.reward)}`}
        </button>
      </div>`;
  }).join("");
  holder.innerHTML = `
    <div class="rounds-log-head"><strong>${escapeHtml(t("season.title"))}</strong><span>${escapeHtml(t("season.level"))} ${formatNumber(currentLevel)} / ${formatNumber(season.max_level || 50)}</span></div>
    <div class="season-track" id="seasonTrack">${cells}</div>
    ${passActive ? "" : `<small class="season-hint">${escapeHtml(t("season.passHint"))}</small>`}`;
  $$("#seasonPanel .season-claim").forEach((button) => {
    button.addEventListener("click", () => claimSeasonReward(Number(button.dataset.seasonLevel), button.dataset.seasonTier));
  });
  const strip = $("#seasonTrack");
  const anchor = strip?.querySelector(".season-cell.current") || strip?.querySelector(".season-cell:not(.unlocked)");
  if (strip && anchor) {
    strip.scrollLeft = Math.max(0, anchor.offsetLeft - strip.clientWidth / 2 + anchor.clientWidth / 2);
  }
}

function renderQuests(retention) {
  const list = $("#questList");
  if (!list) return;
  const quests = retention.quests || [];
  const claimedCount = quests.filter((quest) => quest.claimed).length;
  list.innerHTML = `<div class="rounds-log-head"><strong>${escapeHtml(t("retention.quests"))}</strong><span>${claimedCount}/${quests.length}</span></div>` +
    quests.map((quest) => {
      const progress = `${formatNumber(quest.progress)}/${formatNumber(quest.target)}`;
      const disabled = !quest.complete || quest.claimed;
      const label = quest.claimed ? t("retention.claimed") : t("retention.claim");
      return `
        <div class="quest-item ${quest.claimed ? "claimed" : quest.complete ? "complete" : ""}">
          <span>
            <strong>${escapeHtml(t(`retention.quest.${quest.id}`))}</strong>
            ${progressBar(quest.progress, quest.target)}
            <small>${progress} · +${formatNumber(quest.reward)} ${coinName}</small>
          </span>
          <button type="button" data-quest-id="${escapeHtml(quest.id)}" ${disabled ? "disabled" : ""}>${escapeHtml(label)}</button>
        </div>
      `;
    }).join("");
  $$("#questList button[data-quest-id]").forEach((button) => button.addEventListener("click", () => claimQuest(button.dataset.questId)));
}

const ACHIEVEMENT_ICONS = {
  first_win: "🏆",
  games_50: "🎮",
  games_250: "🎯",
  games_1000: "👑",
  wins_100: "🥇",
  big_x10: "💥",
  streak_7: "🔥",
  streak_30: "🌋",
  invite_3: "🤝",
  invite_10: "🚀",
  all_games: "🧩",
  total_bet_100k: "💰",
};

function renderAchievements(retention) {
  const holder = $("#achievementPanel");
  if (!holder) return;
  const items = retention.achievements || [];
  if (!items.length) {
    holder.innerHTML = "";
    return;
  }
  const claimedCount = items.filter((item) => item.claimed).length;
  holder.innerHTML = `
    <div class="rounds-log-head"><strong>${escapeHtml(t("ach.title"))}</strong><span>${claimedCount}/${items.length}</span></div>
    <div class="achievement-grid">` +
    items.map((item) => {
      const state = item.claimed ? "claimed" : item.complete ? "ready" : "";
      return `
        <div class="achievement-card ${state}">
          <span class="ach-icon" aria-hidden="true">${ACHIEVEMENT_ICONS[item.id] || "⭐"}</span>
          <strong>${escapeHtml(t(`ach.${item.id}`))}</strong>
          ${progressBar(item.progress, item.target)}
          <small>${formatNumber(item.progress)}/${formatNumber(item.target)} · +${formatNumber(item.reward)} ${coinName}</small>
          <button type="button" data-achievement-id="${escapeHtml(item.id)}" ${item.complete && !item.claimed ? "" : "disabled"}>
            ${escapeHtml(item.claimed ? t("retention.claimed") : t("retention.claim"))}
          </button>
        </div>`;
    }).join("") + `</div>`;
  $$("#achievementPanel button[data-achievement-id]").forEach((button) => {
    button.addEventListener("click", () => claimAchievement(button.dataset.achievementId));
  });
}

async function claimQuest(questId) {
  try {
    const body = await api("/api/retention/quests/claim", {
      method: "POST",
      body: JSON.stringify({ quest_id: questId })
    });
    playSound("win");
    if (body.user) setBalance(body.user.balance);
    renderRetention(body.retention);
    showResult($("#retentionResult"), `+${formatNumber(body.claim.reward)} ${coinName}`, true);
  } catch (error) {
    showResult($("#retentionResult"), error.message, false);
  }
}

async function claimAchievement(achievementId) {
  try {
    const body = await api("/api/retention/achievements/claim", {
      method: "POST",
      body: JSON.stringify({ achievement_id: achievementId })
    });
    playSound("win");
    if (body.user) setBalance(body.user.balance);
    renderRetention(body.retention);
    showResult($("#retentionResult"), `${ACHIEVEMENT_ICONS[achievementId] || "⭐"} +${formatNumber(body.claim.reward)} ${coinName}`, true);
  } catch (error) {
    showResult($("#retentionResult"), error.message, false);
  }
}

async function claimSeasonReward(level, tier) {
  try {
    const body = await api("/api/retention/season/claim", {
      method: "POST",
      body: JSON.stringify({ level, tier })
    });
    playSound("win");
    if (body.user) setBalance(body.user.balance);
    renderRetention(body.retention);
    showResult($("#retentionResult"), `Lv ${level} ${tier === "premium" ? "★" : ""} +${formatNumber(body.claim.reward)} ${coinName}`, true);
  } catch (error) {
    showResult($("#retentionResult"), error.message, false);
  }
}

function renderCosmetics(retention) {
  const holder = $("#cosmeticList");
  if (!holder) return;
  const cosmetics = retention.cosmetics || [];
  if (!cosmetics.length) {
    holder.innerHTML = "";
    return;
  }
  holder.innerHTML = `
    <div class="rounds-log-head"><strong>${escapeHtml(t("retention.cosmetics"))}</strong><span>${escapeHtml(retention.active_cosmetic || t("retention.default"))}</span></div>
    <div class="cosmetic-buttons">
      <button type="button" data-cosmetic-id="">${escapeHtml(t("retention.default"))}</button>
      ${cosmetics.map((item) => `<button type="button" data-cosmetic-id="${escapeHtml(item.cosmetic_id)}">${escapeHtml(cosmeticTitle(item.cosmetic_id))}</button>`).join("")}
    </div>
  `;
  $$("#cosmeticList button").forEach((button) => {
    const id = button.dataset.cosmeticId || "";
    button.classList.toggle("active", id === (retention.active_cosmetic || ""));
    button.addEventListener("click", () => selectCosmetic(id));
  });
}

async function selectCosmetic(cosmeticId) {
  try {
    const body = await api("/api/settings/cosmetic", {
      method: "POST",
      body: JSON.stringify({ cosmetic_id: cosmeticId })
    });
    currentUser = body.user || currentUser;
    renderRetention(body.retention);
    showResult($("#retentionResult"), t("retention.cosmeticSaved"), true);
  } catch (error) {
    showResult($("#retentionResult"), error.message, false);
  }
}

function applyCosmeticState(cosmeticId) {
  document.body.classList.toggle("cosmetic-neon-theme", cosmeticId === "neon_theme");
  document.body.classList.toggle("cosmetic-gold-ball", cosmeticId === "gold_ball");
}

function cosmeticTitle(cosmeticId) {
  const map = {
    neon_theme: "Neon table",
    gold_ball: "Gold ball",
  };
  return map[cosmeticId] || cosmeticId;
}

async function loadProfile() {
  if (!initData) return;
  try {
    const body = await api("/api/profile");
    currentUser = body.user || currentUser;
    currentStats = body.stats || currentStats;
    appLimits = body.limits || appLimits;
    if (body.user) setBalance(body.user.balance);
    if (body.bonus) renderBonus(body.bonus);
    if (body.wheel) renderWheel(body.wheel);
    $("#profileInviteLink").value = body.invite_link || "";
    renderProfile();
  } catch (error) {
    showResult($("#profileResult"), error.message, false);
  }
}

function renderProfile() {
  const holder = $("#profileStats");
  if (!holder) return;
  const user = currentUser || {};
  const stats = currentStats || {};
  const rows = [
    [t("profile.status"), intValue(user.is_banned) ? t("profile.blocked") : t("profile.active")],
    [t("profile.games"), formatNumber(stats.games_count)],
    [t("profile.wins"), `${formatNumber(stats.wins_count)} / ${formatNumber(stats.losses_count)}`],
    [t("profile.totalBet"), `${formatNumber(stats.total_bet)} ${coinName}`],
    [t("profile.best"), `${formatNumber(stats.best_payout)} ${coinName}`],
    [t("profile.refs"), formatNumber(user.referral_count)],
    [t("profile.limit"), `${formatNumber(appLimits.min_bet)}-${formatNumber(appLimits.max_bet)} ${coinName}`],
  ];
  holder.innerHTML = rows.map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
  const toggle = $("#bonusNotifyToggle");
  if (toggle) toggle.checked = intValue(user.bonus_notify_enabled) !== 0;
  applyBetLimits();
}

function bindProfile() {
  $("#bonusNotifyToggle").addEventListener("change", async (event) => {
    const enabled = event.target.checked;
    try {
      const body = await api("/api/settings/bonus-notify", {
        method: "POST",
        body: JSON.stringify({ enabled })
      });
      currentUser = body.user || currentUser;
      renderProfile();
      showResult($("#profileResult"), t("profile.saved"), true);
    } catch (error) {
      event.target.checked = !enabled;
      showResult($("#profileResult"), error.message, false);
    }
  });
  $("#copyProfileInvite").addEventListener("click", async () => {
    const value = $("#profileInviteLink").value;
    try {
      await navigator.clipboard.writeText(value);
      showResult($("#profileResult"), t("invite.copied"), true);
    } catch (_) {
      $("#profileInviteLink").select();
    }
  });
}

function maybeShowOnboarding(user) {
  if (!user?.legal_accepted_at) return;
  if (localStorage.getItem("kazartOnboardingSeen") === "1") return;
  $("#onboardingModal").hidden = false;
}

function bindOnboarding() {
  $("#closeOnboarding").addEventListener("click", () => {
    localStorage.setItem("kazartOnboardingSeen", "1");
    $("#onboardingModal").hidden = true;
    playSound("click");
  });
}

// --- Share / brag system ---
const BIGWIN_THRESHOLDS = { upgrader: 3, dice: 3, plinko: 5, crash: 5, roulette: 5 };
const BIGWIN_DAILY_LIMIT = 2;
let lastShareContext = null;

function shareText(game, multiplier, amount) {
  const key = `share.${game}`;
  const template = i18n[currentLang]?.[key] ? key : "share.generic";
  return t(template, { x: Number(multiplier).toFixed(2).replace(/\.?0+$/, ""), amount: formatNumber(amount) });
}

function openShare(game, multiplier, amount) {
  const link = currentInviteLink || (config.publicWebappUrl || "");
  const text = shareText(game, multiplier, amount);
  playSound("click");
  if (link) {
    const url = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`;
    if (tg?.openTelegramLink) tg.openTelegramLink(url);
    else window.open(url, "_blank");
  } else if (navigator.share) {
    navigator.share({ text }).catch(() => {});
  }
}

function bigWinBudgetLeft() {
  const today = new Date().toISOString().slice(0, 10);
  let state = {};
  try { state = JSON.parse(localStorage.getItem("kazartBigWin") || "{}"); } catch (_) {}
  if (state.date !== today) return BIGWIN_DAILY_LIMIT;
  return Math.max(0, BIGWIN_DAILY_LIMIT - (state.count || 0));
}

function consumeBigWinBudget() {
  const today = new Date().toISOString().slice(0, 10);
  let state = {};
  try { state = JSON.parse(localStorage.getItem("kazartBigWin") || "{}"); } catch (_) {}
  if (state.date !== today) state = { date: today, count: 0 };
  state.count = (state.count || 0) + 1;
  localStorage.setItem("kazartBigWin", JSON.stringify(state));
}

// Called on every win. Arms the per-result share button, and pops the
// celebration modal for big multipliers up to BIGWIN_DAILY_LIMIT times a day.
function registerWin(game, multiplier, amount) {
  if (!amount || amount <= 0) return;
  lastShareContext = { game, multiplier, amount };
  const shareBtn = $(`#${game}Share`);
  if (shareBtn) shareBtn.hidden = false;
  const threshold = BIGWIN_THRESHOLDS[game] || 5;
  if (Number(multiplier) >= threshold && bigWinBudgetLeft() > 0) {
    showBigWin(game, multiplier, amount);
  }
}

function clearShare(game) {
  const shareBtn = $(`#${game}Share`);
  if (shareBtn) shareBtn.hidden = true;
}

function showBigWin(game, multiplier, amount) {
  consumeBigWinBudget();
  lastShareContext = { game, multiplier, amount };
  $("#bigWinMultiplier").textContent = `x${Number(multiplier).toFixed(2).replace(/\.?0+$/, "")}`;
  $("#bigWinAmount").textContent = `+${formatNumber(amount)} ${coinName}`;
  const modal = $("#bigWinModal");
  modal.hidden = false;
  modal.querySelector(".bigwin-card").classList.remove("pop");
  void modal.offsetWidth;
  modal.querySelector(".bigwin-card").classList.add("pop");
  playSound("win");
}

function bindShare() {
  Object.keys(BIGWIN_THRESHOLDS).forEach((game) => {
    const button = $(`#${game}Share`);
    if (button) button.addEventListener("click", () => {
      if (lastShareContext && lastShareContext.game === game) {
        openShare(game, lastShareContext.multiplier, lastShareContext.amount);
      }
    });
  });
  $("#bigWinShare")?.addEventListener("click", () => {
    if (lastShareContext) openShare(lastShareContext.game, lastShareContext.multiplier, lastShareContext.amount);
    $("#bigWinModal").hidden = true;
  });
  $("#bigWinClose")?.addEventListener("click", () => {
    $("#bigWinModal").hidden = true;
    playSound("click");
  });
}

function applyBetLimits() {
  ["#upgraderBet", "#diceBet", "#plinkoBet", "#crashBet", "#rouletteBet"].forEach((selector) => {
    const input = $(selector);
    if (!input) return;
    input.min = String(appLimits.min_bet || 1);
    input.max = String(appLimits.max_bet || 100000);
  });
}

function gameTitle(value) {
  const raw = String(value || "");
  return raw ? raw.charAt(0).toUpperCase() + raw.slice(1) : t("history.game");
}

function balanceEventTitle(value) {
  const map = {
    daily_bonus: "Daily bonus",
    daily_bonus_renew: "Daily bonus renew",
    referral: "Referral",
    quest_reward: "Quest reward",
    achievement: "Achievement",
    season_reward: "Season reward",
    stars_shop: "Stars shop",
    stars_refund: "Stars refund",
    admin_adjustment: "Admin adjustment",
    wheel_bonus: "Wheel of fortune",
    weekly_reward: "Weekly top reward",
    admin_ban: "Account block",
    admin_unban: "Account unblock",
  };
  return map[value] || t("history.balance");
}

function formatDateTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString(localeTag(), {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function intValue(value) {
  return Number.parseInt(value || 0, 10) || 0;
}

function escapeHtml(value) {
  return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

bindLanguageSwitch();
bindBetSteppers();
bindSoundToggle();
bindLegalGate();
bindTabs();
bindViewOpeners();
bindUpgrader();
bindDice();
bindPlinko();
bindCrash();
bindRoulette();
bindBonusInvite();
bindWheel();
bindLeaderboard();
bindHistory();
bindProfile();
bindOnboarding();
bindShare();
requestAnimationFrame(updateLiveGameUi);
loadMe();
