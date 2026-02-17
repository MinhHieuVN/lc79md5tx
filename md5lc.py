import os, time, json, threading, random, datetime
import requests
from collections import Counter
from flask import Flask, jsonify
from telegram import Bot, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("8575818729:AAHdWOdvWDCDdyT-M7vQkEwAgA1VqNkbLbQ")
API_URL = "https://lc79-ejw6.onrender.com/lc79/md5"

DATA_USERS = "users.json"   # {chat_id: {role, expire}}
DATA_KEYS  = "keys.json"    # {key: {role, days, used}}
DATA_ADMINS= "admins.json"  # [chat_id]
DATA_HISTORY="history.json"

STATE = {"last_phien": None}

def load(p, d):
    if os.path.exists(p):
        with open(p,"r",encoding="utf-8") as f: return json.load(f)
    return d

def save(p, d):
    with open(p,"w",encoding="utf-8") as f: json.dump(d,f,ensure_ascii=False,indent=2)

users = load(DATA_USERS, {})
keys = load(DATA_KEYS, {})
admins = set(load(DATA_ADMINS, []))
history = load(DATA_HISTORY, [])

def is_admin(cid): return str(cid) in admins

def role_of(cid):
    u = users.get(str(cid))
    if not u: return "FREE"
    if u.get("expire"):
        exp = datetime.date.fromisoformat(u["expire"])
        if exp < datetime.date.today():
            users[str(cid)] = {"role":"FREE","expire":None}
            save(DATA_USERS, users)
            return "FREE"
    return u.get("role","FREE")

def set_role(cid, role, days):
    exp = (datetime.date.today()+datetime.timedelta(days=days)).isoformat()
    users[str(cid)] = {"role":role, "expire":exp}
    save(DATA_USERS, users)

def get_api():
    r = requests.get(API_URL, timeout=10)
    r.raise_for_status()
    return r.json()

def predict():
    if not history: return random.choice(["Tài","Xỉu"]), 0.5
    recent = history[-20:]
    tai = sum(1 for x in recent if x["ket_qua"]=="Tài")
    maj = "Tài" if tai >= len(recent)-tai else "Xỉu"
    if len(recent)>=3:
        last3=[x["ket_qua"] for x in recent[-3:]]
        if last3.count(last3[0])==3:
            flip="Xỉu" if last3[0]=="Tài" else "Tài"
        else: flip=maj
    else: flip=maj
    votes=Counter({maj:1.2, flip:1.0})
    best=votes.most_common(1)[0][0]
    conf=votes[best]/sum(votes.values())
    return best, conf

# -------- Commands (User) --------
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    users.setdefault(str(cid), {"role":"FREE","expire":None})
    save(DATA_USERS, users)
    await update.message.reply_text(
        "👋 Chào bạn!\n"
        "/me – xem trạng thái\n"
        "/predict – dự đoán\n"
        "/stats – thống kê\n"
        "/history – lịch sử (VIP/PRO)\n"
        "/pricing – bảng giá\n"
        "/redeem KEY – kích hoạt VIP/PRO"
    )

async def me(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    r = role_of(cid)
    exp = users.get(str(cid),{}).get("expire")
    await update.message.reply_text(f"👤 Role: {r}\n⏳ Hết hạn: {exp or '-'}")

async def pricing(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💎 BẢNG GIÁ\n"
        "VIP: nhận kèo khi ≥75% | xem 20 lịch sử\n"
        "VIP PRO: nhận kèo sớm khi ≥65% | full history\n"
        "Liên hệ admin để mua key."
    )

async def redeem(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    if not ctx.args:
        await update.message.reply_text("Dùng: /redeem KEY")
        return
    key = ctx.args[0].strip()
    k = keys.get(key)
    if not k or k.get("used"):
        await update.message.reply_text("❌ Key không hợp lệ/đã dùng.")
        return
    set_role(cid, k["role"], k["days"])
    keys[key]["used"] = True
    save(DATA_KEYS, keys)
    await update.message.reply_text(f"✅ Kích hoạt {k['role']} {k['days']} ngày!")

async def predict_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    pred, conf = predict()
    await update.message.reply_text(f"🤖 {pred} ({conf*100:.1f}%)")

async def stats_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not history:
        await update.message.reply_text("Chưa có dữ liệu.")
        return
    tai = sum(1 for x in history if x["ket_qua"]=="Tài")
    await update.message.reply_text(f"📊 Tổng {len(history)} | Tài {tai} | Xỉu {len(history)-tai}")

async def history_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    r = role_of(cid)
    if r == "FREE":
        await update.message.reply_text("🔒 Tính năng VIP/PRO.")
        return
    recent = history if r=="PRO" else history[-20:]
    lines = [f"{x['phien']}: {x['ket_qua']}({x['tong']})" for x in recent[-50:]]
    await update.message.reply_text("\n".join(lines) or "Chưa có lịch sử.")

# -------- Admin --------
async def addadmin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    if not is_admin(cid): return
    aid = ctx.args[0]
    admins.add(aid); save(DATA_ADMINS, list(admins))
    await update.message.reply_text(f"Đã thêm admin {aid}")

async def deladmin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    if not is_admin(cid): return
    aid = ctx.args[0]
    admins.discard(aid); save(DATA_ADMINS, list(admins))
    await update.message.reply_text(f"Đã xoá admin {aid}")

async def genkey(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    if not is_admin(cid): return
    role = ctx.args[0].lower() if ctx.args else "vip"
    days = int(ctx.args[1]) if len(ctx.args)>1 else 30
    role = "PRO" if role=="pro" else "VIP"
    key = f"{role}-{days}D-" + "".join(random.choice("ABCDEFGH0123456789") for _ in range(6))
    keys[key] = {"role": role, "days": days, "used": False}
    save(DATA_KEYS, keys)
    await update.message.reply_text(f"🔑 Key mới: {key}")

async def keys_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    if not is_admin(cid): return
    await update.message.reply_text("\n".join([f"{k}: {v}" for k,v in keys.items()]))

async def grant(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    if not is_admin(cid): return
    uid = ctx.args[0]; role = ctx.args[1].upper(); days = int(ctx.args[2])
    set_role(uid, role, days)
    await update.message.reply_text(f"Đã cấp {role} {days} ngày cho {uid}")

async def revoke(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    if not is_admin(cid): return
    uid = ctx.args[0]
    users[str(uid)]={"role":"FREE","expire":None}; save(DATA_USERS, users)
    await update.message.reply_text(f"Đã thu hồi VIP/PRO của {uid}")

# -------- Loop --------
async def main_loop(bot: Bot):
    while True:
        try:
            data = get_api()
            phien = data["phien"]
            if phien != STATE["last_phien"]:
                history.append({"phien":phien,"tong":data["tong"],"ket_qua":data["ket_qua"]})
                save(DATA_HISTORY, history)
                pred, conf = predict()
                msg = f"🎲 {phien} | {data['ket_qua']}({data['tong']})\n🤖 {pred} ({conf*100:.1f}%)"
                for cid in list(users.keys()):
                    role = role_of(int(cid))
                    th = 0.75 if role=="VIP" else (0.65 if role=="PRO" else 1.1)
                    if role!="FREE" and conf>=th:
                        await bot.send_message(chat_id=int(cid), text=msg)
                STATE["last_phien"] = phien
        except Exception as e:
            print("Loop error:", e)
        time.sleep(10)

# -------- Healthcheck --------
app = Flask(__name__)
@app.route("/")
def health(): return jsonify({"ok": True, "users": len(users), "history": len(history)})

def run_http():
    port = int(os.getenv("PORT","10000"))
    app.run(host="0.0.0.0", port=port)

def boot():
    import asyncio
    threading.Thread(target=run_http, daemon=True).start()
    bot = Bot(BOT_TOKEN)
    async def runner():
        appx = ApplicationBuilder().token(BOT_TOKEN).build()
        appx.add_handler(CommandHandler("start", start))
        appx.add_handler(CommandHandler("me", me))
        appx.add_handler(CommandHandler("pricing", pricing))
        appx.add_handler(CommandHandler("redeem", redeem))
        appx.add_handler(CommandHandler("predict", predict_cmd))
        appx.add_handler(CommandHandler("stats", stats_cmd))
        appx.add_handler(CommandHandler("history", history_cmd))
        appx.add_handler(CommandHandler("addadmin", addadmin))
        appx.add_handler(CommandHandler("deladmin", deladmin))
        appx.add_handler(CommandHandler("genkey", genkey))
        appx.add_handler(CommandHandler("keys", keys_cmd))
        appx.add_handler(CommandHandler("grant", grant))
        appx.add_handler(CommandHandler("revoke", revoke))
        await appx.initialize(); await appx.start(); await appx.bot.initialize(); await appx.run_polling()
    threading.Thread(target=lambda: __import__("asyncio").run(main_loop(bot)), daemon=True).start()
    __import__("asyncio").run(runner())

if __name__ == "__main__":
    boot()
      
