import uuid
from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session
from flask_discord import DiscordOAuth2Session
import platform, os, twitch, json, datetime, requests, sqlite3
from twilio.rest import Client

app = Flask(__name__)
app.secret_key = b"%\xe0'\x01\xdeH\x8e\x85m|\xb3\xffCN\xc9b"
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "true"

# Discord Client : 없으면 서비스 이용 불가
app.config["DISCORD_CLIENT_ID"] = 0
app.config["DISCORD_CLIENT_SECRET"] = ""
app.config["DISCORD_BOT_TOKEN"] = ""
if platform.system() == "Windows":
	app.config["DISCORD_REDIRECT_URI"] = "http://localhost:5000/auth/callback/discord"
	callback_uri = "http://localhost:5000/auth/callback/twitch"
	REDIRECT_URI_MICROSOFT = "http://localhost:5000/auth/callback/microsoft"
else:
	app.config["DISCORD_REDIRECT_URI"] = "https://c.ihah.me/auth/callback/discord"
	callback_uri = "https://c.ihah.me/auth/callback/twitch"
	REDIRECT_URI_MICROSOFT = "https://c.ihah.me/auth/callback/microsoft"
discord = DiscordOAuth2Session(app)

# Twitch Client : 없으면 트위치 관련 서비스 이용 불가
client_id = ""
client_secret = ""
helix = twitch.Helix(client_id, client_secret)

# Twilio Client : 없으면 휴대폰 인증 관련 기능 이용 불가
# Twilio 내에서 MMS용 가상 전화번호를 발급하시고 사용하시길 바랍니다.
client = Client(
    "",
	""
)

# Microsoft Client : 없으면 마인크래프트 계정 인증 불가
microsoftClientID = ""
microsoftClientSecret = ""


@app.route('/')
def index():
	return redirect('/account')

@app.route('/account')
def account():
	discordUser = None ; discordAvatar = None ; discordId = None
	try:
		if discord.authorized:
			discordUser = discord.fetch_user()
			discordAvatar = discordUser.avatar_url
			discordId = discordUser.id
			discordUser = discordUser.username
	except: discord.revoke(); redirect('/account')
	twitch = None ; twitchUser = None ; twitchAvatar = None ; twitchId = None
	if 'TWITCH_ID' in session and session['TWITCH_ID']:
		twitch = helix.user(user=int(session['TWITCH_ID']))
		twitchUser = twitch.display_name
		twitchAvatar = twitch.profile_image_url
		twitchId = session['TWITCH_ID']
	phone = None
	if 'PHONE' in session and session['PHONE']:
		phone = f"{session['PHONE']}"
		if len(phone) == 10: phone = f"0{phone}" ; session['PHONE']=phone
		phone = phone.replace(phone[3:9], "-****-**")
	return render_template('main.html',
		discord=discordUser, discordAvatar=discordAvatar, discordId=discordId,
		twitch=twitchUser, twitchAvatar=twitchAvatar, twitchId=twitchId,
		phone=phone, join=request.args.get("join")
	)

@app.route('/auth/login/phone', methods=['POST'])
def phoneLoginPost():
	phone = str(request.json['phone'])
	if len(phone) == 11 or len(phone) == 10:
		phone_number = phone
		if phone.startswith('010'): phone_number = phone[1:]
		verification = client.verify.v2.services('') \
						.verifications \
						.create(to=f'+82{phone_number}', channel='sms')
		if verification.status == 'pending': return jsonify({'status': 200})
		else: return jsonify({'status': 400})
	else:
		return jsonify({'status': 400})

@app.route('/auth/callback/phone', methods=['POST'])
def phoneLoginCallback():
	phone = str(request.json['phone'])
	phone_number = phone
	if phone.startswith('010'): phone_number = phone[1:]
	verification_check = client.verify.v2.services('') \
					.verification_checks \
					.create(to=f'+82{phone_number}', code=request.json['code'])
	if verification_check.status == 'approved':
		conn = sqlite3.connect('account.db');c = conn.cursor()
		c.execute(f"UPDATE account SET phone='{phone}' WHERE discordId={discord.fetch_user().id}")
		conn.commit();conn.close()
		session['PHONE'] = phone
		return jsonify({'status': 200})
	else: return jsonify({'status': 400})

@app.route('/auth/phone')
def phoneLogin():
	conn = sqlite3.connect('account.db');c = conn.cursor()
	c.execute(f"SELECT * FROM account WHERE discordId={discord.fetch_user().id}")
	if c.fetchone():
		return render_template('phone.html')
	else:
		return redirect('/account?error=account_not_exist')

@app.route('/auth/login/discord')
def discordLogin():
	return discord.create_session(scope=['identify', 'guilds', 'guilds.join'])

@app.route('/auth/callback/discord')
def discordLoginCallback():
	discord.callback()
	user = discord.fetch_user()
	conn = sqlite3.connect('account.db')
	c = conn.cursor()
	c.execute(f"SELECT * FROM account WHERE discordId={user.id}")
	n = c.fetchone()
	if n:
		session['TWITCH_ID'] = n[1] if n[1] != '' else None
		session['PHONE'] = n[3]
	else:
		c.execute(f"INSERT INTO account(discordId, email) VALUES({user.id}, '{user.email}')")
		conn.commit();conn.close()
	return redirect('/account')

@app.route('/auth/login/twitch')
def twitchLogin():
	return redirect(f'https://id.twitch.tv/oauth2/authorize?response_type=code&client_id={client_id}&redirect_uri={callback_uri}&scope=user_read+openid+user:read:follows')

@app.route('/auth/callback/twitch')
def twitchLoginCallback():
	code = request.args.get("code")
	if code:
		userId = discord.fetch_user().id
		token = requests.post("https://id.twitch.tv/oauth2/token", data=f"client_id={client_id}&client_secret={client_secret}&code={code}&grant_type=authorization_code&redirect_uri={callback_uri}")
		tk = json.loads(token.text)
		if 'access_token' in tk:
			session['TWITCH_TOKEN'] = tk['access_token']
		else:
			return redirect('/auth/login/twitch')
		info = requests.get("https://id.twitch.tv/oauth2/userinfo", headers={"Authorization": f"Bearer {session['TWITCH_TOKEN']}"})
		i = json.loads(info.text)
		headers = { 'client-id': client_id, 'Authorization': f"Bearer {session['TWITCH_TOKEN']}" }
		follows = requests.get(f"https://api.twitch.tv/helix/channels/followed?user_id={int(i['sub'])}&broadcaster_id=236323884", headers=headers)
		print(follows.text)
		follow = json.loads(follows.text)['total']

		session['TWITCH_ID'] = i['sub']

		conn = sqlite3.connect('account.db')
		c = conn.cursor()
		c.execute(f"SELECT * FROM account WHERE twitchId={userId}")
		c.execute(f"UPDATE account SET twitchId={int(i['sub'])} WHERE discordId={userId}")
		if follow != 0: # 팔로우가 되어 있는지 확인
			error=0
			session['TWITCH_SUCCESS'] = []
			# 계정 생성일 helix.user(int(i['sub'])).data['created_at']
			# 팔로우 날짜 json.loads(follows.text)['data'][0]['followed_at']
			days = datetime.datetime.strptime(helix.user(int(i['sub'])).data['created_at'], '%Y-%m-%dT%H:%M:%SZ')
			if (datetime.datetime.now() - days).days < 7: # 계정 생성일 7일
				session['TWITCH_SUCCESS'].append('accountCreate')
				error += 1
			days = datetime.datetime.strptime(json.loads(follows.text)['data'][0]['followed_at'], '%Y-%m-%dT%H:%M:%SZ')
			if (datetime.datetime.now() - days).days < 1: # 팔로우 1일
				session['TWITCH_SUCCESS'].append('followDays')
				error += 1
			if error == 0:
				session['TWITCH_SUCCESS'] = True
				c.execute(f"UPDATE account SET ok=1 WHERE discordId={userId}")
		else:
			session['TWITCH_SUCCESS'] = ['follow']
		conn.commit();conn.close()
	if 'NEXT_REDIRECT' in session: return redirect('/redirect')
	else: return redirect('/account')

@app.route('/redirect')
def redirectPage():
	if 'NEXT_REDIRECT' in session:
		_redirect = session['NEXT_REDIRECT']
		del session['NEXT_REDIRECT']
		if _redirect != None: return redirect(_redirect)
	else: return redirect('/account')

@app.route('/auth/login/microsoft')
def microsoftLogin():
	return redirect(f"https://login.live.com/oauth20_authorize.srf?client_id={microsoftClientID}&response_type=code&redirect_uri={REDIRECT_URI_MICROSOFT}&scope=XboxLive.signin%20offline_access&state=0")

@app.route('/auth/callback/microsoft')
def microsoftLoginCallback():
	code = request.args.get("code")
	token = requests.post(
		"https://login.live.com/oauth20_token.srf",
		data=f"client_id={microsoftClientID}&client_secret={microsoftClientSecret}&code={code}&grant_type=authorization_code&redirect_uri={REDIRECT_URI_MICROSOFT}",
		headers={"Content-Type": "application/x-www-form-urlencoded"}
	)
	r = token.json()

	body = {
		"Properties": {
			"AuthMethod": "RPS",
			"SiteName": "user.auth.xboxlive.com",
			"RpsTicket": f"d={r['access_token']}" # 안되면 d= 추가
		},
		"RelyingParty": "http://auth.xboxlive.com",
		"TokenType": "JWT"
	}
	xbox = requests.post(
		"https://user.auth.xboxlive.com/user/authenticate",
		data=f"{body}", headers={"Content-Type": "application/json", "Accept": "application/json"}
	)
	r = xbox.json()
	uhs = r['DisplayClaims']['xui'][0]['uhs']

	body = {
		"Properties": {
			"SandboxId": "RETAIL",
			"UserTokens": [
				r['Token']
			]
		},
		"RelyingParty": "rp://api.minecraftservices.com/",
		"TokenType": "JWT"
	}
	xsts = requests.post(
		"https://xsts.auth.xboxlive.com/xsts/authorize",
		data=f"{body}", headers={"Content-Type": "application/json", "Accept": "application/json"}
	)
	r = xsts.json()
	if xsts.status_code == 200: token = r['Token']
	else: return redirect('/account?error=xbox_account')
	
	body = {
		"identityToken" : f"XBL3.0 x={uhs};{token}",
		"ensureLegacyEnabled" : True
	}
	minecraft = requests.post("https://api.minecraftservices.com/authentication/login_with_xbox", data=f"{body}".replace("'", '"').replace(": True", ": true"))
	print(minecraft.json())

@app.route('/account/join')
def joinServer():
	return redirect('/account?join=false')
	user = discord.fetch_user()
	tw = helix.user(int(session['TWITCH_ID']))
	try: discord.bot_request(f"/guilds/<guild_id>/members/{user.id}", method="PUT", json={"access_token": session["DISCORD_OAUTH2_TOKEN"]['access_token']})
	except: pass
	if not 'TWITCH_SUCCESS' in session:
		conn = sqlite3.connect('account.db')
		c = conn.cursor()
		c.execute(f"SELECT ok FROM account WHERE discordId={user.id}")
		if c.fetchone()[0] == 1:
			session['NEXT_REDIRECT'] = '/account/join'
			return redirect('/auth/login/twitch')
	elif session['TWITCH_SUCCESS'] != True:
		embed = {
			"title": "[웹v2] 조건 불충족 인증자 알림",
			"description": f"<@{user.id}>님이 조건 불충족 계정 `{tw.display_name}`(`{tw.login}`)로 인증하였습니다.\n사유: {session['TWITCH_SUCCESS']}",
			"color": 11259375,
			"footer": {
				"text": "이 메시지는 해당 인증자의 신분이 확인될 경우 삭제해도 돼요."
			}
		}
		try: discord.bot_request(f"/channels/<administration_channel_id>/messages", method="POST", json={"embeds": [embed]})
		except: pass
	embed = {
		"title": "[웹v2] 인증완료 알림",
		"description": f"<@{user.id}>님이 `{tw.display_name}`(`{tw.login}`)로 인증하였습니다.",
		"color": 11259375
	}
	try: discord.bot_request(f"/channels/<administration_channel_id>/messages", method="POST", json={"embeds": [embed]})
	except: pass
	return redirect('/account?join=true')

@app.route('/random')
def random():
	return render_template('random.html')

@app.route('/public/<directory>/<path>')
def public(directory, path):
	return send_from_directory(f'public/{directory}', path)

@app.route('/box/<file>')
@app.route('/box/<directory>/<file>')
def sendfile(file, directory=None):
	file = file.replace("%20", " ")
	if not directory:
		if str(file).endswith('.mp4') != True:
			return send_from_directory(os.path.join(app.root_path, 'box'), f'{file}')#, mimetype='image/vnd.microsoft.icon')
		else:
			return send_from_directory(os.path.join(app.root_path, 'box'), f'{file}', mimetype='video/mp4')
	else:
		directory = directory.replace("%20", " ")
		if str(file).endswith('.mp4') != True:
			return send_from_directory(os.path.join(app.root_path, 'box', directory), f'{file}')#, mimetype='image/vnd.microsoft.icon')
		else:
			return send_from_directory(os.path.join(app.root_path, 'box', directory), f'{file}', mimetype='video/mp4')

app.run(debug=True)