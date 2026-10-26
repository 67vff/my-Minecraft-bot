import os, re, time, uuid, threading, sqlite3
import telebot, requests, urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================
# КОНФИГ
# ============================================================

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '8000630493'))
GIGACHAT_AUTH_KEY = os.getenv('GIGACHAT_AUTH_KEY')
CHANNEL_ID = os.getenv('CHANNEL_ID')
CHAT_ID = os.getenv('CHAT_ID')
CHANNEL_LINK = os.getenv('CHANNEL_LINK', '')
CHAT_LINK = os.getenv('CHAT_LINK', '')

CLAN_NAME = "Мой клан"
POST_LIMIT = 5
POST_WINDOW = 5 * 3600
ADMIN_NICK = "Makakawo777"

RANKS = ["Глава", "Зам", "Старейшина", "Участник"]

PERMISSIONS = [
    ("invite", "Приглашать игроков"),
    ("kick", "Кикать игроков"),
    ("setbase", "Устанавливать базу"),
    ("tp", "Телепорт на базу"),
    ("delbase", "Удалять базу"),
    ("rank", "Изменять ранги"),
    ("treasury_add", "Пополнять казну"),
    ("treasury_sub", "Снимать монеты"),
    ("pvp", "Управлять PvP"),
    ("glow", "Управлять подсветкой"),
    ("levelup", "Повышать уровень"),
    ("renameclan", "Переименовывать клан"),
    ("shop", "Покупать в магазине"),
]

bot = telebot.TeleBot(BOT_TOKEN)
DB_PATH = "/app/data/clan.db"

print(f"[CONFIG] BOT_TOKEN: {'OK' if BOT_TOKEN else 'MISSING!'}", flush=True)
print(f"[CONFIG] GIGACHAT: {'OK' if GIGACHAT_AUTH_KEY else 'MISSING'}", flush=True)
print(f"[CONFIG] CHANNEL_ID: {CHANNEL_ID or 'MISSING'}", flush=True)
print(f"[CONFIG] CHAT_ID: {CHAT_ID or 'MISSING'}", flush=True)
print(f"[CONFIG] CHANNEL_LINK: {'OK' if CHANNEL_LINK else 'MISSING'}", flush=True)
print(f"[CONFIG] CHAT_LINK: {'OK' if CHAT_LINK else 'MISSING'}", flush=True)
print(f"[CONFIG] ADMIN_ID: {ADMIN_ID}", flush=True)


# ============================================================
# БАЗА
# ============================================================

def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.execute("PRAGMA busy_timeout=30000")
    return c


def init_db():
    c = get_conn(); cur = c.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("""CREATE TABLE IF NOT EXISTS players (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_nick TEXT UNIQUE,
        tg_id INTEGER DEFAULT 0,
        tg_username TEXT DEFAULT '',
        rank TEXT DEFAULT 'Участник',
        reputation INTEGER DEFAULT 0,
        treasury INTEGER DEFAULT 0,
        notes TEXT DEFAULT '',
        registered INTEGER DEFAULT 0,
        muted INTEGER DEFAULT 0,
        post_count INTEGER DEFAULT 0,
        post_window_start INTEGER DEFAULT 0,
        created INTEGER
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS permissions (
        player_id INTEGER, perm TEXT, enabled INTEGER DEFAULT 0,
        PRIMARY KEY (player_id, perm))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action TEXT, actor TEXT DEFAULT '', details TEXT DEFAULT '', created INTEGER)""")
    c.commit(); c.close()


init_db()
print("[DB] OK", flush=True)


# ============================================================
# ЛОГ
# ============================================================

def log_action(action, actor="", details=""):
    c = get_conn(); c.cursor().execute(
        "INSERT INTO log (action, actor, details, created) VALUES (?, ?, ?, ?)",
        (action, actor, details, int(time.time())))
    c.commit(); c.close()


# ============================================================
# ИГРОКИ
# ============================================================

def get_player_by_nick(nick):
    c = get_conn(); cur = c.cursor()
    cur.execute("""SELECT id, game_nick, tg_id, tg_username, rank, reputation, treasury, notes,
        registered, muted, post_count, post_window_start FROM players WHERE game_nick=?""", (nick,))
    r = cur.fetchone(); c.close(); return r


def get_player_by_tg(tg_id):
    c = get_conn(); cur = c.cursor()
    cur.execute("""SELECT id, game_nick, tg_id, tg_username, rank, reputation, treasury, notes,
        registered, muted, post_count, post_window_start FROM players WHERE tg_id=?""", (tg_id,))
    r = cur.fetchone(); c.close(); return r


def add_player(nick, rank="Участник"):
    c = get_conn(); cur = c.cursor()
    cur.execute("INSERT OR IGNORE INTO players (game_nick, rank, created) VALUES (?, ?, ?)",
                (nick, rank, int(time.time())))
    c.commit()
    cur.execute("SELECT id FROM players WHERE game_nick=?", (nick,))
    pid = cur.fetchone()[0]
    for perm, _ in PERMISSIONS:
        cur.execute("INSERT OR IGNORE INTO permissions (player_id, perm, enabled) VALUES (?, ?, 0)", (pid, perm))
    c.commit(); c.close()


def register_player(nick, tg_id, tg_username):
    c = get_conn(); c.cursor().execute(
        "UPDATE players SET tg_id=?, tg_username=?, registered=1 WHERE game_nick=?",
        (tg_id, tg_username, nick))
    c.commit(); c.close()


def delete_player(nick):
    c = get_conn(); cur = c.cursor()
    cur.execute("SELECT id FROM players WHERE game_nick=?", (nick,))
    r = cur.fetchone()
    if r:
        pid = r[0]
        cur.execute("DELETE FROM permissions WHERE player_id=?", (pid,))
        cur.execute("DELETE FROM players WHERE id=?", (pid,))
        c.commit()
    c.close()


def update_player(nick, field, value):
    c = get_conn(); c.cursor().execute(f"UPDATE players SET {field}=? WHERE game_nick=?", (value, nick))
    c.commit(); c.close()


def get_permissions(player_id):
    c = get_conn(); cur = c.cursor()
    cur.execute("SELECT perm, enabled FROM permissions WHERE player_id=?", (player_id,))
    rows = dict(cur.fetchall()); c.close(); return rows


def set_permission(player_id, perm, enabled):
    c = get_conn(); c.cursor().execute(
        "INSERT OR REPLACE INTO permissions (player_id, perm, enabled) VALUES (?, ?, ?)",
        (player_id, perm, 1 if enabled else 0))
    c.commit(); c.close()


def all_players():
    c = get_conn(); cur = c.cursor()
    cur.execute("SELECT id, game_nick, tg_id, tg_username, rank, reputation, treasury, notes, registered FROM players ORDER BY id")
    rows = cur.fetchall(); c.close(); return rows


# ============================================================
# АВТО-АДМИН
# ============================================================

def ensure_admin_player():
    p = get_player_by_nick(ADMIN_NICK)
    if not p:
        add_player(ADMIN_NICK, "Глава")
        register_player(ADMIN_NICK, ADMIN_ID, "")
        print(f"[INIT] Админ {ADMIN_NICK} добавлен как Глава", flush=True)
    else:
        if p[2] != ADMIN_ID or p[8] != 1:
            register_player(ADMIN_NICK, ADMIN_ID, "")
        if p[4] != "Глава":
            update_player(ADMIN_NICK, "rank", "Глава")
    p = get_player_by_nick(ADMIN_NICK)
    if p:
        for perm, _ in PERMISSIONS:
            set_permission(p[0], perm, 1)
        print(f"[INIT] Все права выданы {ADMIN_NICK}", flush=True)


ensure_admin_player()


# ============================================================
# ПРОВЕРКА ПОДПИСКИ
# ============================================================

def check_subscription(user_id):
    results = {}
    for name, chat_id in [("channel", CHANNEL_ID), ("chat", CHAT_ID)]:
        if not chat_id:
            results[name] = True
            continue
        try:
            member = bot.get_chat_member(chat_id, user_id)
            results[name] = member.status in ('creator', 'administrator', 'member')
        except Exception:
            results[name] = False
    return results


def send_subscription_gate(chat_id, user_id):
    subs = check_subscription(user_id)
    missing = []
    if not subs.get("channel"):
        missing.append("📺 канал")
    if not subs.get("chat"):
        missing.append("💬 чат")

    if not missing:
        show_main_menu(chat_id)
        return

    m = telebot.types.InlineKeyboardMarkup()
    if not subs.get("channel") and CHANNEL_LINK:
        m.add(telebot.types.InlineKeyboardButton("📺 Подписаться на канал", url=CHANNEL_LINK))
    if not subs.get("chat") and CHAT_LINK:
        m.add(telebot.types.InlineKeyboardButton("💬 Вступить в чат", url=CHAT_LINK))
    m.add(telebot.types.InlineKeyboardButton("✅ Я подписался", callback_data="check_subs"))

    bot.send_message(chat_id,
        f"⚠️ <b>Для доступа нужно подписаться:</b>\n\n"
        f"Не хватает: {', '.join(missing)}\n\n"
        f"Нажми кнопки ниже, а потом «✅ Я подписался».",
        parse_mode='HTML', reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data == "check_subs")
def cb_check_subs(c):
    bot.answer_callback_query(c.id)
    subs = check_subscription(c.from_user.id)
    if subs.get("channel") and subs.get("chat"):
        try:
            bot.delete_message(c.message.chat.id, c.message.message_id)
        except Exception:
            pass
        show_main_menu(c.message.chat.id)
    else:
        bot.answer_callback_query(c.id, "❌ Ты ещё не подписался везде!", show_alert=True)


# ============================================================
# GIGACHAT
# ============================================================

_giga = {"t": None, "e": 0}
_glock = threading.Lock()


def giga_token():
    now = time.time()
    if _giga["t"] and now < _giga["e"]:
        return _giga["t"]
    with _glock:
        try:
            r = requests.post("https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json",
                         "RqUID": str(uuid.uuid4()), "Authorization": f"Basic {GIGACHAT_AUTH_KEY}"},
                data={"scope": "GIGACHAT_API_PERS"}, verify=False, timeout=30)
            t = r.json().get("access_token")
            if t:
                _giga["t"] = t; _giga["e"] = now + 1800; return t
        except Exception as e:
            print(f"[GIGA] {e}")
    return None


def ai_ask(prompt):
    tok = giga_token()
    if not tok:
        return "⚠️ ИИ временно недоступен."
    try:
        r = requests.post("https://api.giga.chat/v1/chat/completions",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {tok}"},
            json={"model": "GigaChat-2", "messages": [{"role": "user", "content": prompt}], "max_tokens": 300},
            verify=False, timeout=30)
        print(f"[AI] {r.status_code}: {r.text[:300]}", flush=True)
        data = r.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "Нет ответа")
    except Exception as e:
        return f"⚠️ Ошибка ИИ: {e}"


def ai_check(text):
    if not text:
        return True, "OK"
    if re.search(r'https?://|t\.me/|www\.', text, re.I):
        return False, "Ссылки запрещены"
    for w in ["хуй", "пизд", "ебал", "бляд", "сука", "fuck", "shit"]:
        if w in text.lower():
            return False, "Мат запрещён"
    return True, "OK"


def send_to_channel(text, photo_id=None, author=""):
    if not CHANNEL_ID:
        return False, "Канал не настроен"
    try:
        signature = f"\n\n👤 Отправил: <b>{author}</b>" if author else ""
        full_text = text + signature
        if photo_id:
            bot.send_photo(CHANNEL_ID, photo_id, caption=full_text, parse_mode='HTML')
        else:
            bot.send_message(CHANNEL_ID, full_text, parse_mode='HTML')
        return True, "OK"
    except Exception as e:
        return False, str(e)


# ============================================================
# КОМАНДЫ В ЧАТЕ
# ============================================================

@bot.message_handler(commands=['help'])
def cmd_help(message):
    if str(message.chat.id) != str(CHAT_ID) and message.chat.id != ADMIN_ID:
        return
    bot.reply_to(message,
        "📋 <b>Команды</b>\n\n"
        "/ai вопрос — спросить ИИ\n"
        "/ai сколько игроков — кол-во + ники\n"
        "/ai ники — список ников\n"
        "/ai ник репутация — репутация\n"
        "/me — профиль\n"
        "/clan — список клана\n"
        "/help — справка",
        parse_mode='HTML')


@bot.message_handler(commands=['me'])
def cmd_me(message):
    p = get_player_by_tg(message.from_user.id)
    if not p:
        bot.reply_to(message, "❌ Ты не зарегистрирован.")
        return
    perms = get_permissions(p[0])
    perm_text = "\n".join([f"{'✅' if perms.get(k, 0) else '❌'} {v}" for k, v in PERMISSIONS])
    bot.reply_to(message,
        f"👤 <b>{p[1]}</b>\n🎖 Ранг: {p[4]}\n⭐ Репутация: {p[5]}\n💰 Казна: {p[6]}\n\n"
        f"<b>Права:</b>\n{perm_text}",
        parse_mode='HTML')


@bot.message_handler(commands=['clan'])
def cmd_clan(message):
    players = all_players()
    if not players:
        bot.reply_to(message, "📭 В клане пока нет игроков.")
        return
    lines = [f"🏰 <b>{CLAN_NAME}</b> — {len(players)} игроков\n"]
    for p in players:
        status = "✅" if p[8] else "⏳"
        lines.append(f"{status} {p[1]} — {p[4]} ⭐{p[5]}")
    bot.reply_to(message, "\n".join(lines), parse_mode='HTML')


@bot.message_handler(commands=['ai'])
def cmd_ai(message):
    if str(message.chat.id) != str(CHAT_ID) and message.chat.id != ADMIN_ID:
        return
    args = message.text.replace('/ai', '').strip()
    if not args:
        bot.reply_to(message, "🤖 " + ai_ask("Привет! Чем помочь?"))
        return
    p = get_player_by_tg(message.from_user.id)
    if not p:
        bot.reply_to(message, "❌ Ты не зарегистрирован. Попроси админа добавить тебя.")
        return
    if p[9]:
        bot.reply_to(message, "🔇 Ты заглушён, не можешь использовать /ai.")
        return
    low = args.lower()
    if "сколько игроков" in low:
        players = all_players()
        nicks = ", ".join([x[1] for x in players]) if players else "0"
        bot.reply_to(message, f"👥 Игроков: {len(players)}\n{nicks}")
        return
    if "ники" in low or "список" in low:
        players = all_players()
        nicks = ", ".join([x[1] for x in players]) if players else "пусто"
        bot.reply_to(message, f"📝 Ники: {nicks}")
        return
    if "репутация" in low:
        for w in args.split():
            target = get_player_by_nick(w)
            if target:
                bot.reply_to(message, f"⭐ {target[1]} — репутация: {target[5]}, ранг: {target[4]}")
                return
        bot.reply_to(message, "❌ Игрок не найден.")
        return
    bot.reply_to(message, "🤖 " + ai_ask(args))


# ============================================================
# РЕГИСТРАЦИЯ
# ============================================================

@bot.message_handler(commands=['start'])
def start(message):
    p = get_player_by_tg(message.from_user.id)
    if p and p[8]:
        send_subscription_gate(message.chat.id, message.from_user.id)
        return
    m = telebot.types.InlineKeyboardMarkup()
    m.add(telebot.types.InlineKeyboardButton("📝 Зарегистрироваться", callback_data="reg"))
    bot.send_message(message.chat.id, "👋 Ты не зарегистрирован.\n\nНажми кнопку и введи свой игровой ник.", reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data == "reg")
def cb_reg(c):
    bot.answer_callback_query(c.id)
    s = bot.send_message(c.message.chat.id, "Введи свой игровой ник (как в игре):")
    bot.register_next_step_handler(s, process_reg)


def process_reg(message):
    nick = (message.text or "").strip()
    p = get_player_by_nick(nick)
    if not p:
        bot.send_message(message.chat.id, "❌ Такого ника нет в клане. Обратись к админу.")
        return
    if p[8]:
        bot.send_message(message.chat.id, "❌ Этот ник уже занят.")
        return
    m = telebot.types.InlineKeyboardMarkup()
    m.add(telebot.types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{p[0]}_{message.from_user.id}"))
    m.add(telebot.types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{p[0]}_{message.from_user.id}"))
    uname = f"@{message.from_user.username}" if message.from_user.username else ""
    bot.send_message(ADMIN_ID,
        f"🆕 <b>Заявка</b>\nНик: {nick}\nTG: {uname}\nID: {message.from_user.id}",
        parse_mode='HTML', reply_markup=m)
    bot.send_message(message.chat.id, "✅ Заявка отправлена админу. Жди одобрения.")


@bot.callback_query_handler(func=lambda c: c.data.startswith("approve_"))
def cb_approve(c):
    if c.from_user.id != ADMIN_ID:
        bot.answer_callback_query(c.id, "Не админ", show_alert=True); return
    parts = c.data.split("_")
    pid, tg_id = int(parts[1]), int(parts[2])
    c2 = get_conn(); cur = c2.cursor()
    cur.execute("SELECT game_nick FROM players WHERE id=?", (pid,))
    r = cur.fetchone(); c2.close()
    if not r:
        bot.answer_callback_query(c.id, "Игрок не найден"); return
    nick = r[0]
    register_player(nick, tg_id, "")
    log_action("register", str(tg_id), nick)
    bot.answer_callback_query(c.id, "Одобрено")
    try:
        bot.send_message(tg_id, f"✅ Ты зарегистрирован как <b>{nick}</b>!", parse_mode='HTML')
        send_subscription_gate(tg_id, tg_id)
    except Exception:
        pass
    try:
        bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("reject_"))
def cb_reject(c):
    if c.from_user.id != ADMIN_ID:
        bot.answer_callback_query(c.id, "Не админ", show_alert=True); return
    parts = c.data.split("_")
    tg_id = int(parts[2])
    bot.answer_callback_query(c.id, "Отклонено")
    try:
        bot.send_message(tg_id, "❌ Заявка отклонена админом.")
    except Exception:
        pass
    try:
        bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)
    except Exception:
        pass

# ============================================================
# ГЛАВНОЕ МЕНЮ
# ============================================================

def show_main_menu(chat_id):
    p = get_player_by_tg(chat_id)
    if not p:
        return
    m = telebot.types.InlineKeyboardMarkup()
    m.add(telebot.types.InlineKeyboardButton("👤 Мой профиль", callback_data="me"))
    m.add(telebot.types.InlineKeyboardButton("🏰 Список клана", callback_data="clan_list"))
    m.add(telebot.types.InlineKeyboardButton("🤖 Спросить ИИ", callback_data="ai_menu"))
    m.add(telebot.types.InlineKeyboardButton("📢 Отправить пост в канал", callback_data="post_menu"))
    if p[2] == ADMIN_ID:
        m.add(telebot.types.InlineKeyboardButton("👑 Админ-панель", callback_data="admin"))
    bot.send_message(chat_id,
        f"💎 <b>{CLAN_NAME}</b>\n\n👤 {p[1]}\n🎖 {p[4]}\n⭐ {p[5]}\n💰 {p[6]}",
        parse_mode='HTML', reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data == "menu")
def cb_menu(c):
    bot.answer_callback_query(c.id)
    p = get_player_by_tg(c.from_user.id)
    if not p:
        return
    m = telebot.types.InlineKeyboardMarkup()
    m.add(telebot.types.InlineKeyboardButton("👤 Мой профиль", callback_data="me"))
    m.add(telebot.types.InlineKeyboardButton("🏰 Список клана", callback_data="clan_list"))
    m.add(telebot.types.InlineKeyboardButton("🤖 Спросить ИИ", callback_data="ai_menu"))
    m.add(telebot.types.InlineKeyboardButton("📢 Отправить пост в канал", callback_data="post_menu"))
    if p[2] == ADMIN_ID:
        m.add(telebot.types.InlineKeyboardButton("👑 Админ-панель", callback_data="admin"))
    try:
        bot.edit_message_text(f"💎 <b>{CLAN_NAME}</b>\n\nВыбери действие 👇",
            chat_id=c.message.chat.id, message_id=c.message.message_id,
            parse_mode='HTML', reply_markup=m)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data == "me")
def cb_me(c):
    bot.answer_callback_query(c.id)
    p = get_player_by_tg(c.from_user.id)
    if not p:
        return
    perms = get_permissions(p[0])
    perm_lines = "\n".join([f"{'✅' if perms.get(k, 0) else '❌'} {v}" for k, v in PERMISSIONS])
    m = telebot.types.InlineKeyboardMarkup().add(telebot.types.InlineKeyboardButton("⬅️ В меню", callback_data="menu"))
    try:
        bot.edit_message_text(
            f"👤 <b>{p[1]}</b>\n🎖 Ранг: {p[4]}\n⭐ Репутация: {p[5]}\n💰 Казна: {p[6]}\n\n"
            f"<b>Права:</b>\n{perm_lines}\n\n<b>Заметки:</b> {p[7] or '—'}",
            chat_id=c.message.chat.id, message_id=c.message.message_id,
            parse_mode='HTML', reply_markup=m)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data == "clan_list")
def cb_clan_list(c):
    bot.answer_callback_query(c.id)
    players = all_players()
    m = telebot.types.InlineKeyboardMarkup()
    for p in players:
        m.add(telebot.types.InlineKeyboardButton(f"{p[1]} ({p[4]})", callback_data=f"pinfo_{p[0]}"))
    m.add(telebot.types.InlineKeyboardButton("⬅️ В меню", callback_data="menu"))
    lines = [f"🏰 <b>{CLAN_NAME}</b> — {len(players)} игроков\n"]
    for p in players:
        lines.append(f"{'✅' if p[8] else '⏳'} {p[1]} — {p[4]} ⭐{p[5]}")
    try:
        bot.edit_message_text("\n".join(lines), chat_id=c.message.chat.id,
            message_id=c.message.message_id, parse_mode='HTML', reply_markup=m)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("pinfo_"))
def cb_pinfo(c):
    bot.answer_callback_query(c.id)
    pid = int(c.data.split("_")[1])
    c2 = get_conn(); cur = c2.cursor()
    cur.execute("SELECT game_nick, rank, reputation, treasury, notes, registered FROM players WHERE id=?", (pid,))
    r = cur.fetchone(); c2.close()
    if not r:
        return
    m = telebot.types.InlineKeyboardMarkup().add(telebot.types.InlineKeyboardButton("⬅️ Назад", callback_data="clan_list"))
    try:
        bot.edit_message_text(
            f"👤 <b>{r[0]}</b>\n🎖 {r[1]}\n⭐ {r[2]}\n💰 {r[3]}\n"
            f"{'✅ Зарегистрирован' if r[5] else '⏳ Не зарегистрирован'}\n📝 {r[4] or '—'}",
            chat_id=c.message.chat.id, message_id=c.message.message_id,
            parse_mode='HTML', reply_markup=m)
    except Exception:
        pass


# ============================================================
# ИИ-МЕНЮ
# ============================================================

@bot.callback_query_handler(func=lambda c: c.data == "ai_menu")
def cb_ai_menu(c):
    bot.answer_callback_query(c.id)
    m = telebot.types.InlineKeyboardMarkup()
    m.add(telebot.types.InlineKeyboardButton("📊 Сколько игроков", callback_data="ai_count"))
    m.add(telebot.types.InlineKeyboardButton("📝 Ники всех", callback_data="ai_nicks"))
    m.add(telebot.types.InlineKeyboardButton("⭐ Репутация игрока", callback_data="ai_rep_list"))
    m.add(telebot.types.InlineKeyboardButton("💬 Свой вопрос", callback_data="ai_free"))
    m.add(telebot.types.InlineKeyboardButton("⬅️ В меню", callback_data="menu"))
    try:
        bot.edit_message_text("🤖 <b>Спросить ИИ</b>", chat_id=c.message.chat.id,
            message_id=c.message.message_id, parse_mode='HTML', reply_markup=m)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data == "ai_count")
def cb_ai_count(c):
    bot.answer_callback_query(c.id)
    players = all_players()
    nicks = ", ".join([x[1] for x in players]) if players else "пусто"
    m = telebot.types.InlineKeyboardMarkup().add(telebot.types.InlineKeyboardButton("⬅️ Назад", callback_data="ai_menu"))
    try:
        bot.edit_message_text(f"👥 Игроков: {len(players)}\n{nicks}",
            chat_id=c.message.chat.id, message_id=c.message.message_id, reply_markup=m)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data == "ai_nicks")
def cb_ai_nicks(c):
    bot.answer_callback_query(c.id)
    players = all_players()
    nicks = "\n".join([f"• {x[1]}" for x in players]) if players else "пусто"
    m = telebot.types.InlineKeyboardMarkup().add(telebot.types.InlineKeyboardButton("⬅️ Назад", callback_data="ai_menu"))
    try:
        bot.edit_message_text(f"📝 Ники:\n{nicks}",
            chat_id=c.message.chat.id, message_id=c.message.message_id, reply_markup=m)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data == "ai_rep_list")
def cb_ai_rep_list(c):
    bot.answer_callback_query(c.id)
    players = all_players()
    m = telebot.types.InlineKeyboardMarkup()
    for p in players:
        m.add(telebot.types.InlineKeyboardButton(p[1], callback_data=f"ai_rep_{p[0]}"))
    m.add(telebot.types.InlineKeyboardButton("⬅️ Назад", callback_data="ai_menu"))
    try:
        bot.edit_message_text("Выбери игрока:", chat_id=c.message.chat.id,
            message_id=c.message.message_id, reply_markup=m)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("ai_rep_"))
def cb_ai_rep(c):
    bot.answer_callback_query(c.id)
    pid = int(c.data.split("_")[2])
    c2 = get_conn(); cur = c2.cursor()
    cur.execute("SELECT game_nick, reputation, rank FROM players WHERE id=?", (pid,))
    r = cur.fetchone(); c2.close()
    m = telebot.types.InlineKeyboardMarkup().add(telebot.types.InlineKeyboardButton("⬅️ Назад", callback_data="ai_rep_list"))
    try:
        bot.edit_message_text(f"⭐ {r[0]} — репутация: {r[1]}, ранг: {r[2]}",
            chat_id=c.message.chat.id, message_id=c.message.message_id, reply_markup=m)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data == "ai_free")
def cb_ai_free(c):
    bot.answer_callback_query(c.id)
    s = bot.send_message(c.message.chat.id, "💬 Напиши свой вопрос:")
    bot.register_next_step_handler(s, process_ai_free)


def process_ai_free(message):
    p = get_player_by_tg(message.from_user.id)
    if not p or p[9]:
        return
    bot.send_message(message.chat.id, "🤖 " + ai_ask(message.text))
    show_main_menu(message.chat.id)


# ============================================================
# ПОСТ В КАНАЛ
# ============================================================

@bot.callback_query_handler(func=lambda c: c.data == "post_menu")
def cb_post_menu(c):
    bot.answer_callback_query(c.id)
    p = get_player_by_tg(c.from_user.id)
    if not p:
        return
    now = int(time.time())
    if now - p[11] > POST_WINDOW:
        update_player(p[1], "post_count", 0)
        update_player(p[1], "post_window_start", now)
        p = get_player_by_tg(c.from_user.id)
    if c.from_user.id != ADMIN_ID and p[10] >= POST_LIMIT:
        bot.send_message(c.message.chat.id, f"❌ Лимит: {POST_LIMIT} постов в 5 часов.")
        return
    s = bot.send_message(c.message.chat.id, "📢 Отправь текст поста или фото с подписью:")
    bot.register_next_step_handler(s, process_post)


def process_post(message):
    p = get_player_by_tg(message.from_user.id)
    if not p:
        return
    text = (message.text or message.caption or "").strip()
    if not text:
        bot.send_message(message.chat.id, "❌ Нужен текст или подпись.")
        return
    ok, r = ai_check(text)
    if not ok:
        bot.send_message(message.chat.id, f"❌ ИИ: {r}")
        return
    if message.from_user.id != ADMIN_ID:
        now = int(time.time())
        if now - p[11] > POST_WINDOW:
            update_player(p[1], "post_count", 0)
            update_player(p[1], "post_window_start", now)
            p = get_player_by_tg(message.from_user.id)
        if p[10] >= POST_LIMIT:
            bot.send_message(message.chat.id, f"❌ Лимит: {POST_LIMIT} постов в 5 часов.")
            return
    photo_id = message.photo[-1].file_id if message.photo else None
    ok2, err = send_to_channel(text, photo_id, author=p[1])
    if ok2:
        if message.from_user.id != ADMIN_ID:
            update_player(p[1], "post_count", p[10] + 1)
        log_action("post", p[1], text[:100])
        bot.send_message(message.chat.id, "✅ Пост опубликован.")
        show_main_menu(message.chat.id)
    else:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {err}")


# ============================================================
# АДМИН-ПАНЕЛЬ
# ============================================================

@bot.callback_query_handler(func=lambda c: c.data == "admin")
def cb_admin(c):
    if c.from_user.id != ADMIN_ID:
        bot.answer_callback_query(c.id, "Не админ", show_alert=True); return
    bot.answer_callback_query(c.id)
    m = telebot.types.InlineKeyboardMarkup()
    m.add(telebot.types.InlineKeyboardButton("👥 Игроки", callback_data="adm_players"))
    m.add(telebot.types.InlineKeyboardButton("🎖 Ранги", callback_data="adm_ranks"))
    m.add(telebot.types.InlineKeyboardButton("💰 Казна", callback_data="adm_treasury"))
    m.add(telebot.types.InlineKeyboardButton("📝 Лог", callback_data="adm_log"))
    m.add(telebot.types.InlineKeyboardButton("📤 Экспорт", callback_data="adm_export"))
    m.add(telebot.types.InlineKeyboardButton("⬅️ В меню", callback_data="menu"))
    try:
        bot.edit_message_text("👑 <b>Админ-панель</b>", chat_id=c.message.chat.id,
            message_id=c.message.message_id, parse_mode='HTML', reply_markup=m)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data == "adm_players")
def cb_adm_players(c):
    if c.from_user.id != ADMIN_ID:
        return
    bot.answer_callback_query(c.id)
    m = telebot.types.InlineKeyboardMarkup()
    m.add(telebot.types.InlineKeyboardButton("➕ Добавить игрока", callback_data="adm_add"))
    m.add(telebot.types.InlineKeyboardButton("📋 Список", callback_data="adm_list"))
    m.add(telebot.types.InlineKeyboardButton("⬅️ Назад", callback_data="admin"))
    try:
        bot.edit_message_text("👥 <b>Игроки</b>", chat_id=c.message.chat.id,
            message_id=c.message.message_id, parse_mode='HTML', reply_markup=m)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data == "adm_add")
def cb_adm_add(c):
    if c.from_user.id != ADMIN_ID:
        return
    bot.answer_callback_query(c.id)
    s = bot.send_message(c.message.chat.id, "Введи ник нового игрока:")
    bot.register_next_step_handler(s, adm_add_nick)


def adm_add_nick(message):
    nick = (message.text or "").strip()
    if not nick:
        return
    add_player(nick)
    log_action("add_player", "admin", nick)
    bot.send_message(message.chat.id, f"✅ Игрок {nick} добавлен. Теперь он может зарегистрироваться.")


@bot.callback_query_handler(func=lambda c: c.data == "adm_list")
def cb_adm_list(c):
    if c.from_user.id != ADMIN_ID:
        return
    bot.answer_callback_query(c.id)
    players = all_players()
    m = telebot.types.InlineKeyboardMarkup()
    for p in players:
        m.add(telebot.types.InlineKeyboardButton(p[1], callback_data=f"adm_p_{p[0]}"))
    m.add(telebot.types.InlineKeyboardButton("⬅️ Назад", callback_data="adm_players"))
    try:
        bot.edit_message_text("Выбери игрока:", chat_id=c.message.chat.id,
            message_id=c.message.message_id, reply_markup=m)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_p_"))
def cb_adm_p(c):
    if c.from_user.id != ADMIN_ID:
        return
    bot.answer_callback_query(c.id)
    pid = int(c.data.split("_")[2])
    c2 = get_conn(); cur = c2.cursor()
    cur.execute("SELECT game_nick, rank, reputation, treasury, notes, registered FROM players WHERE id=?", (pid,))
    r = cur.fetchone(); c2.close()
    if not r:
        return
    m = telebot.types.InlineKeyboardMarkup()
    m.add(telebot.types.InlineKeyboardButton("✏️ Ранг", callback_data=f"adm_rank_{pid}"))
    m.add(telebot.types.InlineKeyboardButton("✅ Права", callback_data=f"adm_perms_{pid}"))
    m.add(telebot.types.InlineKeyboardButton("📝 Заметки", callback_data=f"adm_note_{pid}"))
    m.add(telebot.types.InlineKeyboardButton("💰 Казна", callback_data=f"adm_treas_{pid}"))
    m.add(telebot.types.InlineKeyboardButton("🔇 Мут /ai", callback_data=f"adm_mute_{pid}"))
    m.add(telebot.types.InlineKeyboardButton("🗑 Удалить", callback_data=f"adm_del_{pid}"))
    m.add(telebot.types.InlineKeyboardButton("⬅️ Назад", callback_data="adm_list"))
    try:
        bot.edit_message_text(
            f"👤 <b>{r[0]}</b>\n🎖 {r[1]}\n⭐ {r[2]}\n💰 {r[3]}\n"
            f"{'✅ Зарегистрирован' if r[5] else '⏳ Не зарегистрирован'}\n📝 {r[4] or '—'}",
            chat_id=c.message.chat.id, message_id=c.message.message_id,
            parse_mode='HTML', reply_markup=m)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_rank_"))
def cb_adm_rank(c):
    if c.from_user.id != ADMIN_ID:
        return
    bot.answer_callback_query(c.id)
    pid = int(c.data.split("_")[2])
    m = telebot.types.InlineKeyboardMarkup()
    for r in RANKS:
        m.add(telebot.types.InlineKeyboardButton(r, callback_data=f"setrank_{pid}_{r}"))
    m.add(telebot.types.InlineKeyboardButton("⬅️ Назад", callback_data=f"adm_p_{pid}"))
    try:
        bot.edit_message_text("Выбери ранг:", chat_id=c.message.chat.id,
            message_id=c.message.message_id, reply_markup=m)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("setrank_"))
def cb_setrank(c):
    if c.from_user.id != ADMIN_ID:
        return
    parts = c.data.split("_")
    pid, rank = int(parts[1]), parts[2]
    c2 = get_conn(); cur = c2.cursor()
    cur.execute("SELECT game_nick FROM players WHERE id=?", (pid,))
    nick = cur.fetchone()[0]
    update_player(nick, "rank", rank)
    log_action("set_rank", "admin", f"{nick} -> {rank}")
    bot.answer_callback_query(c.id, f"Ранг: {rank}")
    cb_adm_p(c)


@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_perms_"))
def cb_adm_perms(c):
    if c.from_user.id != ADMIN_ID:
        return
    bot.answer_callback_query(c.id)
    pid = int(c.data.split("_")[2])
    perms = get_permissions(pid)
    m = telebot.types.InlineKeyboardMarkup()
    for k, v in PERMISSIONS:
        icon = "✅" if perms.get(k, 0) else "❌"
        m.add(telebot.types.InlineKeyboardButton(f"{icon} {v}", callback_data=f"toggle_{pid}_{k}"))
    m.add(telebot.types.InlineKeyboardButton("⬅️ Назад", callback_data=f"adm_p_{pid}"))
    try:
        bot.edit_message_text("Права игрока:", chat_id=c.message.chat.id,
            message_id=c.message.message_id, reply_markup=m)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("toggle_"))
def cb_toggle(c):
    if c.from_user.id != ADMIN_ID:
        return
    parts = c.data.split("_")
    pid, perm = int(parts[1]), parts[2]
    perms = get_permissions(pid)
    new = 0 if perms.get(perm, 0) else 1
    set_permission(pid, perm, new)
    bot.answer_callback_query(c.id, "✅" if new else "❌")
    cb_adm_perms(c)


@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_note_"))
def cb_adm_note(c):
    if c.from_user.id != ADMIN_ID:
        return
    bot.answer_callback_query(c.id)
    pid = int(c.data.split("_")[2])
    s = bot.send_message(c.message.chat.id, "Введи заметку об игроке:")
    bot.register_next_step_handler(s, lambda m: adm_note_save(m, pid))


def adm_note_save(message, pid):
    c2 = get_conn(); cur = c2.cursor()
    cur.execute("SELECT game_nick FROM players WHERE id=?", (pid,))
    r = cur.fetchone(); c2.close()
    if r:
        update_player(r[0], "notes", message.text or "")
        log_action("note", "admin", f"{r[0]}: {message.text}")
    bot.send_message(message.chat.id, "✅ Заметка сохранена.")


@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_treas_"))
def cb_adm_treas(c):
    if c.from_user.id != ADMIN_ID:
        return
    bot.answer_callback_query(c.id)
    pid = int(c.data.split("_")[2])
    s = bot.send_message(c.message.chat.id, "Введи сумму (например 500 или -100):")
    bot.register_next_step_handler(s, lambda m: adm_treas_save(m, pid))


def adm_treas_save(message, pid):
    try:
        amt = int((message.text or "").strip())
    except ValueError:
        bot.send_message(message.chat.id, "❌ Число.")
        return
    c2 = get_conn(); cur = c2.cursor()
    cur.execute("SELECT game_nick, treasury FROM players WHERE id=?", (pid,))
    r = cur.fetchone(); c2.close()
    if not r:
        return
    new = max(0, r[1] + amt)
    update_player(r[0], "treasury", new)
    log_action("treasury", "admin", f"{r[0]}: {amt:+d}")
    bot.send_message(message.chat.id, f"✅ Казна {r[0]}: {new}")


@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_mute_"))
def cb_adm_mute(c):
    if c.from_user.id != ADMIN_ID:
        return
    bot.answer_callback_query(c.id)
    pid = int(c.data.split("_")[2])
    c2 = get_conn(); cur = c2.cursor()
    cur.execute("SELECT game_nick, muted FROM players WHERE id=?", (pid,))
    r = cur.fetchone(); c2.close()
    if not r:
        return
    new = 0 if r[1] else 1
    update_player(r[0], "muted", new)
    bot.answer_callback_query(c.id, "🔇" if new else "🔊")


@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_del_"))
def cb_adm_del(c):
    if c.from_user.id != ADMIN_ID:
        return
    bot.answer_callback_query(c.id)
    pid = int(c.data.split("_")[2])
    c2 = get_conn(); cur = c2.cursor()
    cur.execute("SELECT game_nick FROM players WHERE id=?", (pid,))
    r = cur.fetchone(); c2.close()
    if r:
        delete_player(r[0])
        log_action("delete_player", "admin", r[0])
    bot.send_message(c.message.chat.id, "🗑 Удалён.")


@bot.callback_query_handler(func=lambda c: c.data == "adm_ranks")
def cb_adm_ranks(c):
    if c.from_user.id != ADMIN_ID:
        return
    bot.answer_callback_query(c.id)
    m = telebot.types.InlineKeyboardMarkup()
    for r in RANKS:
        m.add(telebot.types.InlineKeyboardButton(r, callback_data=f"rankview_{r}"))
    m.add(telebot.types.InlineKeyboardButton("⬅️ Назад", callback_data="admin"))
    try:
        bot.edit_message_text("🎖 <b>Ранги</b>", chat_id=c.message.chat.id,
            message_id=c.message.message_id, parse_mode='HTML', reply_markup=m)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("rankview_"))
def cb_rankview(c):
    if c.from_user.id != ADMIN_ID:
        return
    rank = c.data.split("_")[1]
    c2 = get_conn(); cur = c2.cursor()
    cur.execute("SELECT game_nick FROM players WHERE rank=?", (rank,))
    rows = cur.fetchall(); c2.close()
    nicks = "\n".join([f"• {x[0]}" for x in rows]) if rows else "пусто"
    m = telebot.types.InlineKeyboardMarkup().add(telebot.types.InlineKeyboardButton("⬅️ Назад", callback_data="adm_ranks"))
    try:
        bot.edit_message_text(f"🎖 <b>{rank}</b>\n{nicks}", chat_id=c.message.chat.id,
            message_id=c.message.message_id, parse_mode='HTML', reply_markup=m)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data == "adm_treasury")
def cb_adm_treasury(c):
    if c.from_user.id != ADMIN_ID:
        return
    bot.answer_callback_query(c.id)
    c2 = get_conn(); cur = c2.cursor()
    cur.execute("SELECT SUM(treasury) FROM players")
    total = cur.fetchone()[0] or 0
    c2.close()
    m = telebot.types.InlineKeyboardMarkup().add(telebot.types.InlineKeyboardButton("⬅️ Назад", callback_data="admin"))
    try:
        bot.edit_message_text(f"💰 <b>Общая казна:</b> {total}", chat_id=c.message.chat.id,
            message_id=c.message.message_id, parse_mode='HTML', reply_markup=m)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data == "adm_log")
def cb_adm_log(c):
    if c.from_user.id != ADMIN_ID:
        return
    bot.answer_callback_query(c.id)
    c2 = get_conn(); cur = c2.cursor()
    cur.execute("SELECT action, actor, details, created FROM log ORDER BY id DESC LIMIT 20")
    rows = cur.fetchall(); c2.close()
    lines = [f"{time.strftime('%d.%m %H:%M', time.localtime(ts))} — {a} ({act}): {det}" for a, act, det, ts in rows]
    m = telebot.types.InlineKeyboardMarkup().add(telebot.types.InlineKeyboardButton("⬅️ Назад", callback_data="admin"))
    try:
        bot.edit_message_text("📝 <b>Лог</b>\n\n" + ("\n".join(lines) if lines else "Пусто"),
            chat_id=c.message.chat.id, message_id=c.message.message_id,
            parse_mode='HTML', reply_markup=m)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data == "adm_export")
def cb_adm_export(c):
    if c.from_user.id != ADMIN_ID:
        return
    bot.answer_callback_query(c.id)
    c2 = get_conn(); cur = c2.cursor()
    cur.execute("SELECT game_nick, rank, reputation, treasury, registered FROM players")
    rows = cur.fetchall(); c2.close()
    text = "game_nick,rank,reputation,treasury,registered\n"
    for r in rows:
        text += ",".join([str(x) for x in r]) + "\n"
    try:
        bot.send_document(c.message.chat.id, ("players.csv", text.encode('utf-8')))
    except Exception as e:
        bot.send_message(c.message.chat.id, f"⚠️ {e}")


# ============================================================
# ЗАПУСК
# ============================================================

print("[BOT] polling...", flush=True)
while True:
    try:
        bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"[BOT] {e}", flush=True); time.sleep(5)
