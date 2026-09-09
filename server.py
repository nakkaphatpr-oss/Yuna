"""Yuna Clinic: local single-machine application. Python 3.10+, standard library only."""
import base64, datetime as dt, hashlib, hmac, http.cookies, json, math, os, pathlib, secrets, sqlite3, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from database import connect, initialize, ConfigurationError

BASE=pathlib.Path(__file__).resolve().parent
DB=pathlib.Path(os.environ.get('YUNA_DB',str(BASE/'data'/'clinic.db')))
PORT=int(os.environ.get('YUNA_PORT','8765'))
ROLES=['Owner','แพทย์','พยาบาล','Front','คลัง','บัญชี']
ACCESS={'dashboard':ROLES,'patients':['Owner','แพทย์','พยาบาล','Front'],'appointments':['Owner','แพทย์','พยาบาล','Front'],'procedures':['Owner','แพทย์','พยาบาล'],'packages':['Owner','Front'],'inventory':['Owner','แพทย์','พยาบาล','คลัง'],'finance':['Owner','บัญชี','Front'],'fees':['Owner','บัญชี'],'users':['Owner'],'audit':['Owner'],'privacy':['Owner']}
WRITE={'patients':['Owner','แพทย์','พยาบาล','Front'],'clinical':['Owner','แพทย์','พยาบาล'],'appointments':['Owner','แพทย์','พยาบาล','Front'],'procedures':['Owner','แพทย์','พยาบาล'],'packages':['Owner','Front'],'inventory':['Owner','คลัง'],'finance':['Owner','บัญชี','Front'],'users':['Owner'],'privacy':['Owner']}
LOCK=threading.RLock()
CLOUD=bool(os.environ.get('VERCEL') or os.environ.get('YUNA_CLOUD')=='1')
def origins():
    if not CLOUD:return {f'http://localhost:{PORT}',f'http://127.0.0.1:{PORT}'}
    result={os.environ.get('APP_ORIGIN','').rstrip('/')}
    for key in ['VERCEL_URL','VERCEL_PROJECT_PRODUCTION_URL']:
        if os.environ.get(key):result.add('https://'+os.environ[key].strip().rstrip('/'))
    return {origin for origin in result if origin.startswith('https://') and urlparse(origin).netloc and not urlparse(origin).path}
def now():return dt.datetime.now(dt.timezone(dt.timedelta(hours=7))).replace(tzinfo=None).isoformat(timespec='seconds')
def today():return now()[:10]
def rows(c,q,args=()):return [dict(r) for r in c.execute(q,args)]
def one(c,q,args=()):
    r=c.execute(q,args).fetchone();return dict(r) if r else None
def hashpw(p,salt=None):
    salt=salt or secrets.token_hex(16)
    return salt+':'+hashlib.pbkdf2_hmac('sha256',p.encode(),salt.encode(),600000).hex()
def audit(c,u,action,entity='',eid='',detail=''):
    c.execute('INSERT INTO audit(created,user_id,actor,action,entity,entity_id,detail) VALUES(?,?,?,?,?,?,?)',(now(),u.get('id'),u.get('name','ระบบ'),action,entity,str(eid),detail))
def textval(d,k,required=True,limit=2000):
    v=str(d.get(k,'')).strip()
    if required and not v:raise ValueError('กรุณาระบุ '+k)
    if len(v)>limit:raise ValueError('ข้อความยาวเกินกำหนด')
    return v
def number(d,k,minimum=0,integer=False):
    try:v=float(d.get(k,0) or 0)
    except:raise ValueError('จำนวนไม่ถูกต้อง: '+k)
    if not math.isfinite(v) or v<minimum or v>1e10 or (integer and v!=int(v)):raise ValueError('จำนวนไม่ถูกต้อง: '+k)
    return int(v) if integer else v
def validdate(v):
    try:return dt.date.fromisoformat(v).isoformat()
    except:raise ValueError('วันที่ไม่ถูกต้อง')
def patient(c,d):
    p=one(c,'SELECT * FROM patients WHERE id=?',(d.get('patient_id'),))
    if not p:raise ValueError('ไม่พบผู้รับบริการ')
    return p
def allow(u,key,write=False):
    if u['role'] not in (WRITE if write else ACCESS).get(key,[]):raise PermissionError('บทบาทของคุณไม่มีสิทธิ์ใช้งานส่วนนี้')
def init():
    initialize()

class Handler(BaseHTTPRequestHandler):
    server_version='YunaClinic'
    def log_message(self,*args):pass
    def reply(self,data,status=200,headers=None,mime='application/json; charset=utf-8'):
        body=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
        if CLOUD:self.send_header('Strict-Transport-Security','max-age=31536000')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'")
        for k,v in (headers or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(body)
    def user(self,c):
        cookie=http.cookies.SimpleCookie()
        try:cookie.load(self.headers.get('Cookie','')); token=cookie['yuna'].value
        except:raise PermissionError('SESSION')
        s=one(c,'SELECT s.*,u.name,u.username,u.role,u.active FROM sessions s JOIN users u ON u.id=s.user_id WHERE token=?',(hashlib.sha256(token.encode()).hexdigest(),))
        if not s or not s['active'] or time.time()-s['last_seen']>1800 or time.time()-s['created']>28800:raise PermissionError('SESSION')
        c.execute('UPDATE sessions SET last_seen=? WHERE token=?',(time.time(),s['token']))
        if self.command=='POST' and not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),s['csrf']):raise PermissionError('คำขอไม่ถูกต้อง กรุณาเข้าสู่ระบบใหม่')
        return {'id':s['user_id'],'name':s['name'],'role':s['role'],'username':s['username'],'csrf':s['csrf'],'token':s['token'],'expires_at':s['created']+28800}
    def do_GET(self):self.run(False)
    def do_POST(self):self.run(True)
    def run(self,post):
        try:
            host=self.headers.get('Host','')
            if host not in {urlparse(origin).netloc for origin in origins()}:raise PermissionError('Host ไม่ได้รับอนุญาต กรุณาตั้งค่า APP_ORIGIN ให้ตรงกับเว็บไซต์')
            if post:
                origin=self.headers.get('Origin')
                if (CLOUD and not origin) or (origin and origin not in origins()):raise PermissionError('Origin ไม่ได้รับอนุญาต')
            path=urlparse(self.path).path; query=parse_qs(urlparse(self.path).query)
            if not path.startswith('/api/'):
                if post:return self.reply({'error':'ไม่พบหน้า'},404)
                public={'/':'index.html','/index.html':'index.html','/styles.css':'styles.css','/app.js':'app.js','/favicon.svg':'favicon.svg','/yuna-logo.png':'yuna-logo.png'}
                name=public.get(path)
                if not name:return self.reply({'error':'ไม่พบหน้า'},404)
                mime={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.svg':'image/svg+xml','.png':'image/png'}
                return self.reply((BASE/'public'/name).read_bytes(),mime=mime[pathlib.Path(name).suffix])
            d={}
            if post:
                size=int(self.headers.get('Content-Length','0'))
                if size>4000000:raise ValueError('คำขอใหญ่เกินกำหนด เลือกภาพไม่เกิน 2.5 MB')
                d=json.loads(self.rfile.read(size) or b'{}')
                if not isinstance(d,dict):raise ValueError('คำขอไม่ถูกต้อง')
            with LOCK,connect() as c:
                if path=='/api/status' and not post:return self.reply({'setup':c.execute('SELECT COUNT(*) FROM users').fetchone()[0]==0,'setup_token_required':CLOUD})
                if path in ['/api/login','/api/setup'] and post:
                    setup=path.endswith('setup'); ts=time.time()
                    key=hashlib.sha256(textval(d,'username').lower().encode()).hexdigest()
                    c.execute('DELETE FROM login_attempts WHERE created<?',(ts-900,))
                    if c.execute('SELECT COUNT(*) FROM login_attempts WHERE key=?',(key,)).fetchone()[0]>=10:return self.reply({'error':'เข้าสู่ระบบผิดหลายครั้ง กรุณารอ 15 นาที'},429)
                    if setup:
                        if c.execute('SELECT COUNT(*) FROM users').fetchone()[0]:raise PermissionError('ตั้งค่าบัญชีเริ่มต้นแล้ว')
                        if CLOUD:
                            expected=os.environ.get('YUNA_SETUP_TOKEN','')
                            if len(expected)<32:raise ConfigurationError('ผู้ดูแลต้องตั้งค่า YUNA_SETUP_TOKEN ก่อนสร้างบัญชี Owner')
                            if not hmac.compare_digest(expected,textval(d,'setup_token',False)):
                                c.execute('INSERT INTO login_attempts(key,created) VALUES(?,?)',(key,ts));c.commit()
                                raise PermissionError('รหัสตั้งค่า Owner ไม่ถูกต้อง')
                        pw=textval(d,'password')
                        if len(pw)<12:raise ValueError('รหัสผ่านต้องยาวอย่างน้อย 12 ตัวอักษร')
                        c.execute('INSERT INTO users(username,name,role,password) VALUES(?,?,?,?)',(textval(d,'username').lower(),textval(d,'name'),'Owner',hashpw(pw)))
                    u=one(c,'SELECT * FROM users WHERE username=? AND active=1',(textval(d,'username').lower(),))
                    candidate=hashpw(textval(d,'password'),u['password'].split(':')[0] if u else '0'*32)
                    if not u or not hmac.compare_digest(u['password'],candidate):
                        c.execute('INSERT INTO login_attempts(key,created) VALUES(?,?)',(key,ts));audit(c,{},'เข้าสู่ระบบไม่สำเร็จ');c.commit();return self.reply({'error':'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง'},401)
                    c.execute('DELETE FROM login_attempts WHERE key=?',(key,)); token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
                    c.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),u['id'],csrf,ts,ts));audit(c,u,'สร้างบัญชี Owner' if setup else 'เข้าสู่ระบบ');c.commit()
                    return self.reply({'ok':True},headers={'Set-Cookie':f'yuna={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'+('; Secure' if CLOUD else '')})
                u=self.user(c)
                if path=='/api/me' and not post:return self.reply({k:v for k,v in u.items() if k!='token'}|{'views':[k for k,v in ACCESS.items() if u['role'] in v]})
                if path=='/api/logout' and post:
                    c.execute('DELETE FROM sessions WHERE token=?',(u['token'],));audit(c,u,'ออกจากระบบ');c.commit();return self.reply({'ok':True},headers={'Set-Cookie':'yuna=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'+('; Secure' if CLOUD else '')})
                if post:
                    result=self.mutate(c,u,path,d);c.commit();return self.reply(result or {'ok':True})
                result=self.read(c,u,path,query);c.commit()
                if isinstance(result,tuple):return self.reply(result[0],mime=result[1])
                return self.reply(result)
        except ConfigurationError as e:self.reply({'error':str(e)},503)
        except PermissionError as e:self.reply({'error':'กรุณาเข้าสู่ระบบ' if str(e)=='SESSION' else str(e)},401 if str(e)=='SESSION' else 403)
        except (ValueError,KeyError,TypeError,sqlite3.IntegrityError) as e:self.reply({'error':'ข้อมูลซ้ำหรืออ้างอิงไม่ถูกต้อง' if isinstance(e,sqlite3.IntegrityError) else str(e)},400)
        except Exception:self.reply({'error':'ไม่สามารถทำรายการได้ กรุณาตรวจสอบข้อมูลและลองใหม่'},500)
    def read(self,c,u,path,q):
        key=path.split('/')[2];allow(u,key)
        if path=='/api/procedures/face':
            pid=q.get('id',[''])[0]
            face=one(c,'SELECT * FROM procedure_faces WHERE procedure_id=?',(pid,))
            audit(c,u,'เปิด Face Detail / Simulation','procedures',pid)
            return face or {}
        if key=='dashboard':
            result={'patients':c.execute('SELECT COUNT(*) FROM patients').fetchone()[0] if u['role'] in ACCESS['patients'] else None,'appointments':rows(c,'SELECT a.*,p.name FROM appointments a JOIN patients p ON p.id=a.patient_id WHERE substr(start,1,10)=? ORDER BY start',(today(),)) if u['role'] in ACCESS['appointments'] else [],'low':c.execute('SELECT COUNT(*) FROM products p WHERE opening+COALESCE((SELECT SUM(qty) FROM lots WHERE product_id=p.id),0)<=min_stock').fetchone()[0] if u['role'] in ACCESS['inventory'] else None}
            if u['role'] in ['Owner','บัญชี']:
                month=q.get('month',[today()[:7]])[0]
                result.update({'month':month,'totals':rows(c,'SELECT kind,SUM(amount) amount,SUM(source_profit) profit,COUNT(*) n FROM finance WHERE substr(date,1,7)=? GROUP BY kind',(month,)), 'trend':rows(c,"SELECT substr(date,1,7) AS month,SUM(amount) amount FROM finance WHERE kind='receipt' GROUP BY month ORDER BY month DESC LIMIT 8"), 'categories':rows(c,"SELECT description,SUM(amount) amount FROM finance WHERE kind='receipt' AND substr(date,1,7)=? GROUP BY description ORDER BY amount DESC LIMIT 5",(month,)), 'recent':rows(c,"SELECT * FROM finance WHERE kind='receipt' ORDER BY date DESC,id DESC LIMIT 6"),'fees':one(c,'SELECT COALESCE(SUM(doctor_fee+commission),0) amount FROM procedures WHERE substr(created,1,7)=?',(month,))['amount']})
            return result
        if key=='patients':
            pid=q.get('id',[''])[0]
            if pid:
                p=one(c,'SELECT * FROM patients WHERE id=?',(pid,))
                if not p:raise ValueError('ไม่พบผู้รับบริการ')
                if u['role']=='Front':
                    p={k:v for k,v in p.items() if k in ['id','hn','name','nickname','age','phone','member']}
                else:
                    p['consents']=rows(c,'SELECT * FROM consents WHERE patient_id=? ORDER BY id DESC',(pid,));p['photos']=rows(c,'SELECT id,phase,note,created FROM photos WHERE patient_id=?',(pid,));p['procedures']=rows(c,'SELECT * FROM procedures WHERE patient_id=? ORDER BY id DESC',(pid,))
                    if u['role']!='Owner':
                        for record in p['procedures']:
                            for k in ['doctor_fee','commission']:record.pop(k,None)
                audit(c,u,'เปิดเวชระเบียน','patients',pid);return p
            term='%'+q.get('search',[''])[0]+'%'
            return rows(c,'SELECT id,hn,name,nickname,age,phone,member'+(',allergies,conditions,clinical_review' if u['role']!='Front' else '')+' FROM patients WHERE name LIKE ? OR nickname LIKE ? OR hn LIKE ? OR phone LIKE ? ORDER BY id DESC',(term,)*4)
        if key=='appointments':return rows(c,'SELECT a.*,p.name,p.hn,p.nickname FROM appointments a JOIN patients p ON p.id=a.patient_id ORDER BY start')
        if key=='procedures':
            if path=='/api/procedures/photo':
                r=one(c,'SELECT * FROM photos WHERE id=?',(q.get('id',[''])[0],))
                if not r:raise ValueError('ไม่พบภาพ')
                audit(c,u,'เปิดภาพเวชระเบียน','photos',r['id']);return (r['image'],r['mime'])
            procedure_id=q.get('id',[''])[0]
            data=rows(c,'SELECT t.*,p.name,p.hn,p.nickname FROM procedures t JOIN patients p ON p.id=t.patient_id'+(' WHERE t.id=?' if procedure_id else '')+' ORDER BY t.id DESC',(procedure_id,) if procedure_id else ())
            if procedure_id:audit(c,u,'เปิดรายละเอียดหัตถการ','procedures',procedure_id)
            for record in data:
                extra=one(c,'SELECT * FROM procedure_details WHERE procedure_id=?',(record['id'],))
                record['appointment_id']=extra['appointment_id'] if extra else None
                record['has_face']=bool(one(c,'SELECT procedure_id FROM procedure_faces WHERE procedure_id=?',(record['id'],)))
                pricing=one(c,'SELECT * FROM procedure_pricing WHERE procedure_id=?',(record['id'],))
                if pricing:pricing['items']=json.loads(pricing['items'])
                record['pricing']=pricing
                if u['role'] in ACCESS['finance']:
                    record['receipt']=one(c,'SELECT f.*,x.payment_method FROM procedure_payments x JOIN finance f ON f.id=x.finance_id WHERE x.procedure_id=?',(record['id'],))
                if u['role']=='Owner' and extra:
                    record['commission_base']=extra['commission_base'];record['commission_rate']=extra['commission_rate']
                record['lots']=rows(c,'SELECT l.lot,l.expiry,x.qty,p.name FROM procedure_lots x JOIN lots l ON l.id=x.lot_id JOIN products p ON p.id=l.product_id WHERE x.procedure_id=?',(record['id'],))
                if u['role']!='Owner':
                    record.pop('doctor_fee',None);record.pop('commission',None)
            return data
        if key=='packages':return {'packages':rows(c,'SELECT k.*,p.name patient FROM packages k JOIN patients p ON p.id=k.patient_id ORDER BY k.id DESC'),'promotions':rows(c,'SELECT * FROM promotions ORDER BY id DESC'),'redemptions':rows(c,'SELECT r.*,k.name package,p.name patient FROM redemptions r JOIN packages k ON k.id=r.package_id JOIN patients p ON p.id=k.patient_id ORDER BY r.id DESC')}
        if key=='inventory':
            stock=rows(c,'SELECT p.*,opening+COALESCE((SELECT SUM(qty) FROM lots WHERE product_id=p.id),0) stock FROM products p ORDER BY name')
            lots=rows(c,'SELECT l.*,p.name,p.unit FROM lots l JOIN products p ON p.id=l.product_id ORDER BY expiry')
            if u['role'] in ['แพทย์','พยาบาล']:
                for l in lots:l.pop('cost',None)
            return {'products':stock,'lots':lots,'movements':rows(c,'SELECT m.*,l.lot,p.name FROM movements m JOIN lots l ON l.id=m.lot_id JOIN products p ON p.id=l.product_id ORDER BY m.id DESC LIMIT 200'),'legacy':rows(c,'SELECT * FROM source_stock ORDER BY date DESC,id DESC LIMIT 100') if c.execute("SELECT name FROM sqlite_master WHERE name='source_stock'").fetchone() else []}
        if key=='finance':
            if path=='/api/finance/patients':return rows(c,'SELECT id,hn,name FROM patients ORDER BY name')
            data=rows(c,'SELECT f.*,x.payment_method FROM finance f LEFT JOIN procedure_payments x ON x.finance_id=f.id ORDER BY f.date DESC,f.id DESC')
            if u['role']=='Front':
                data=[r for r in data if r['kind']!='expense']
                for r in data:r.pop('source_profit',None)
            return data
        if key=='fees':return rows(c,'SELECT id,created,service,doctor,doctor_fee,staff,commission FROM procedures ORDER BY id DESC')
        if key=='users':return rows(c,'SELECT id,username,name,role,active FROM users ORDER BY id')
        if key=='audit':return rows(c,'SELECT * FROM audit ORDER BY id DESC LIMIT 500')
        if key=='privacy':
            meta=one(c,"SELECT value FROM source_meta WHERE key='import'")
            return {'source':json.loads(meta['value']) if meta else {},'consents':rows(c,'SELECT c.*,p.name FROM consents c JOIN patients p ON p.id=c.patient_id ORDER BY c.id DESC'),'users':rows(c,'SELECT role,COUNT(*) n FROM users WHERE active=1 GROUP BY role')}
        raise ValueError('ไม่พบรายการ')
    def mutate(self,c,u,path,d):
        key=path.split('/')[2];action=path.split('/')[3] if len(path.split('/'))>3 else 'create'
        allow(u,'clinical' if key=='clinical' else key,True)
        eid='';detail=''
        if key=='patients':
            if action=='member':
                p=patient(c,d); member=textval(d,'member')
                if member not in ['Standard','Silver','Gold','Platinum']:raise ValueError('ระดับสมาชิกไม่ถูกต้อง')
                c.execute('UPDATE patients SET member=? WHERE id=?',(member,p['id']));eid=p['id']
            else:
                vals=[textval(d,'hn'),textval(d,'name'),textval(d,'nickname',False),number(d,'age',integer=True),textval(d,'phone',False)]
                if vals[3]>125:raise ValueError('อายุไม่ถูกต้อง')
                eid=c.execute('INSERT INTO patients(hn,name,nickname,age,phone) VALUES(?,?,?,?,?)',vals).lastrowid
        elif key=='clinical':
            p=patient(c,d);eid=p['id']
            if action=='review':
                c.execute('UPDATE patients SET allergies=?,conditions=?,medicines=?,address=?,emergency=?,clinical_review=1 WHERE id=?',tuple(textval(d,k,k in ['allergies','conditions']) for k in ['allergies','conditions','medicines','address','emergency'])+(p['id'],))
            elif action=='consent':
                decision=textval(d,'decision'); purpose=textval(d,'purpose')
                if decision not in ['ยินยอม','ถอนความยินยอม'] or purpose not in ['การรักษา','ภาพก่อน–หลัง']:raise ValueError('ข้อมูลความยินยอมไม่ถูกต้อง')
                c.execute('INSERT INTO consents(patient_id,purpose,version,decision,signed_by,created,actor) VALUES(?,?,?,?,?,?,?)',(p['id'],purpose,textval(d,'version'),decision,textval(d,'signed_by'),now(),u['id']))
            elif action=='photo':
                consent=one(c,"SELECT decision FROM consents WHERE patient_id=? AND purpose='ภาพก่อน–หลัง' ORDER BY id DESC LIMIT 1",(p['id'],))
                if not consent or consent['decision']!='ยินยอม':raise ValueError('ต้องบันทึกความยินยอมสำหรับภาพก่อน–หลังก่อน')
                phase=textval(d,'phase')
                if phase not in ['ก่อนทำ','หลังทำ']:raise ValueError('ประเภทภาพไม่ถูกต้อง')
                try:b=base64.b64decode(d.get('image',''),validate=True)
                except:raise ValueError('ภาพไม่ถูกต้อง')
                mime='image/png' if b.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if b.startswith(b'\xff\xd8\xff') else ''
                if not mime or len(b)>2500000:raise ValueError('รองรับ JPG/PNG ขนาดไม่เกิน 2.5 MB')
                c.execute('INSERT INTO photos(patient_id,phase,note,mime,image,created,actor) VALUES(?,?,?,?,?,?,?)',(p['id'],phase,textval(d,'note',False),mime,b,now(),u['id']))
            else:raise ValueError('ไม่พบคำสั่ง')
        elif key=='appointments':
            if action in ['status','followup']:
                a=one(c,'SELECT * FROM appointments WHERE id=?',(d.get('id'),))
                if not a:raise ValueError('ไม่พบนัดหมาย')
                eid=a['id']
                if action=='status':
                    status=textval(d,'status')
                    if status not in ['รอยืนยัน','ยืนยันแล้ว','รอพบแพทย์','กำลังรับบริการ','เสร็จสิ้น','ยกเลิก']:raise ValueError('สถานะไม่ถูกต้อง')
                    if a['status']=='ยกเลิก' and status!='ยกเลิก':raise ValueError('นัดที่ยกเลิกแล้ว กรุณาสร้างนัดใหม่เพื่อตรวจสอบคิว')
                    c.execute('UPDATE appointments SET status=? WHERE id=?',(status,eid))
                else:c.execute('UPDATE appointments SET followup_note=? WHERE id=?',(textval(d,'followup_note'),eid))
            else:
                p=patient(c,d)
                editing=None
                if action=='edit':
                    editing=one(c,'SELECT * FROM appointments WHERE id=?',(d.get('id'),))
                    if not editing:raise ValueError('ไม่พบนัดหมาย')
                    if editing['status'] in ['ยกเลิก','เสร็จสิ้น']:raise ValueError('ไม่สามารถแก้ไขนัดที่ยกเลิกหรือเสร็จสิ้นแล้ว')
                    if p['id']!=editing['patient_id']:raise ValueError('ไม่สามารถเปลี่ยนผู้รับบริการของนัดเดิม')
                try:start=dt.datetime.fromisoformat(textval(d,'start')); start=start.replace(second=0,microsecond=0)
                except:raise ValueError('วันเวลานัดหมายไม่ถูกต้อง')
                duration=number(d,'duration',1,True)
                if duration>480:raise ValueError('ระยะเวลาต้องไม่เกิน 480 นาที')
                doctor=textval(d,'doctor');room=textval(d,'room');end=start+dt.timedelta(minutes=duration)
                for a in rows(c,"SELECT * FROM appointments WHERE status!='ยกเลิก' AND (doctor=? OR room=? OR patient_id=?)",(doctor,room,p['id'])):
                    if editing and a['id']==editing['id']:continue
                    other=dt.datetime.fromisoformat(a['start'])
                    if start<other+dt.timedelta(minutes=a['duration']) and end>other:raise ValueError('แพทย์ ห้อง หรือผู้รับบริการมีนัดทับซ้อนในช่วงเวลานี้')
                followup=textval(d,'followup',False)
                if followup and validdate(followup)<start.date().isoformat():raise ValueError('วันติดตามต้องไม่ก่อนวันนัด')
                if editing:
                    eid=editing['id']
                    c.execute('UPDATE appointments SET service=?,doctor=?,room=?,start=?,duration=?,followup=? WHERE id=?',(textval(d,'service'),doctor,room,start.isoformat(timespec='minutes'),duration,followup,eid))
                    detail='แก้ไขนัดหมาย: '+json.dumps(dict(editing),ensure_ascii=False)
                else:eid=c.execute('INSERT INTO appointments(patient_id,service,doctor,room,start,duration,followup) VALUES(?,?,?,?,?,?,?)',(p['id'],textval(d,'service'),doctor,room,start.isoformat(timespec='minutes'),duration,followup)).lastrowid
        elif key=='inventory':
            if action=='opening':
                product=one(c,'SELECT * FROM products WHERE id=?',(d.get('product_id'),))
                if not product:raise ValueError('ไม่พบสินค้า')
                opening=number(d,'opening');reason=textval(d,'reason');eid=product['id']
                c.execute('UPDATE products SET opening=? WHERE id=?',(opening,eid))
                detail=f"ยอดเดิม {product['opening']} → ยอดใหม่ {opening} · {reason}"
            elif action=='product':eid=c.execute('INSERT INTO products(code,name,category,unit,min_stock) VALUES(?,?,?,?,?)',(textval(d,'code'),textval(d,'name'),textval(d,'category'),textval(d,'unit'),number(d,'min_stock'))).lastrowid
            elif action=='receive':
                product=one(c,'SELECT * FROM products WHERE id=?',(d.get('product_id'),))
                if not product:raise ValueError('ไม่พบสินค้า')
                qty=number(d,'qty',0.000001);expiry=validdate(textval(d,'expiry'));lot=textval(d,'lot');cost=number(d,'cost')
                if expiry<today():raise ValueError('ไม่สามารถรับ Lot ที่หมดอายุ')
                reconcile=bool(d.get('reconcile'))
                if reconcile and (product['opening']<qty or product['opening']<=0):raise ValueError('จำนวนเกินยอดตั้งต้นที่รอระบุ Lot')
                old=one(c,'SELECT * FROM lots WHERE product_id=? AND lot=?',(product['id'],lot))
                if old:
                    if old['expiry']!=expiry or old['cost']!=cost:raise ValueError('Lot เดิมมีวันหมดอายุหรือต้นทุนต่างกัน')
                    eid=old['id'];c.execute('UPDATE lots SET qty=qty+? WHERE id=?',(qty,eid))
                else:eid=c.execute('INSERT INTO lots(product_id,lot,expiry,qty,cost) VALUES(?,?,?,?,?)',(product['id'],lot,expiry,qty,cost)).lastrowid
                if reconcile:c.execute('UPDATE products SET opening=opening-? WHERE id=?',(qty,product['id']))
                c.execute('INSERT INTO movements(lot_id,qty,reason,created,actor) VALUES(?,?,?,?,?)',(eid,qty,'จัดสรรยอดตั้งต้น' if reconcile else 'รับสินค้า',now(),u['id']))
            elif action=='adjust':
                l=one(c,'SELECT * FROM lots WHERE id=?',(d.get('lot_id'),));qty=number(d,'qty',0.000001)
                if not l or qty>l['qty']:raise ValueError('จำนวนเกินยอดคงเหลือ')
                reason=textval(d,'reason');eid=l['id'];c.execute('UPDATE lots SET qty=qty-? WHERE id=?',(qty,eid));c.execute('INSERT INTO movements(lot_id,qty,reason,created,actor) VALUES(?,?,?,?,?)',(eid,-qty,reason,now(),u['id']))
            else:raise ValueError('ไม่พบคำสั่ง')
        elif key=='procedures':
            if action=='payment-edit':
                allow(u,'finance',True)
                receipt=one(c,"SELECT f.*,x.payment_method FROM procedure_payments x JOIN finance f ON f.id=x.finance_id WHERE x.procedure_id=? AND f.kind='receipt'",(d.get('id'),))
                if not receipt:raise ValueError('ไม่พบใบเสร็จของหัตถการนี้')
                if number(d,'previous_amount')!=receipt['amount']:raise ValueError('ยอดชำระถูกแก้ไขแล้ว กรุณาโหลดข้อมูลล่าสุดก่อน')
                amount=number(d,'amount',0.01);reason=textval(d,'reason')
                c.execute('UPDATE finance SET amount=? WHERE id=?',(amount,receipt['id']))
                audit(c,u,'แก้ไขยอดชำระ','finance',receipt['id'],json.dumps({'ยอดเดิม':receipt['amount'],'ยอดใหม่':amount,'เหตุผล':reason},ensure_ascii=False))
                return {'id':receipt['id']}
            if action=='payment':
                allow(u,'finance',True)
                procedure=one(c,'SELECT t.*,p.name FROM procedures t JOIN patients p ON p.id=t.patient_id WHERE t.id=?',(d.get('id'),))
                if not procedure:raise ValueError('ไม่พบหัตถการ')
                if one(c,'SELECT finance_id FROM procedure_payments WHERE procedure_id=?',(procedure['id'],)):raise ValueError('หัตถการนี้มีใบเสร็จแล้ว กรุณาเปิดพิมพ์จากรายการเดิม')
                method=textval(d,'payment_method')
                if method not in ['เงินสด','โอนเงิน','บัตรเครดิต / เดบิต','QR Payment','อื่น ๆ']:raise ValueError('กรุณาเลือกช่องทางชำระเงิน')
                if d.get('finance_id'):
                    receipt=one(c,"SELECT * FROM finance WHERE id=? AND kind='receipt'",(d['finance_id'],))
                    if not receipt or receipt['patient_id']!=procedure['patient_id']:raise ValueError('ใบเสร็จไม่ตรงกับผู้รับบริการ')
                    if one(c,'SELECT procedure_id FROM procedure_payments WHERE finance_id=?',(receipt['id'],)):raise ValueError('ใบเสร็จนี้เชื่อมกับหัตถการอื่นแล้ว')
                    receipt_id=receipt['id']
                else:
                    if d.get('paid_confirmed') is not True:raise ValueError('กรุณายืนยันว่าได้รับชำระเงินจริงแล้ว')
                    amount=number(d,'amount',0.01)
                    receipt_id=c.execute('INSERT INTO finance(kind,patient_id,customer,description,amount,date,source) VALUES(?,?,?,?,?,?,?)',('receipt',procedure['patient_id'],procedure['name'],procedure['service'],amount,validdate(textval(d,'date')),'หัตถการ #'+str(procedure['id']))).lastrowid
                c.execute('INSERT INTO procedure_payments(procedure_id,finance_id,payment_method) VALUES(?,?,?)',(procedure['id'],receipt_id,method))
                audit(c,u,'รับชำระ / เชื่อมใบเสร็จ','procedures',procedure['id'],'ใบเสร็จ #'+str(receipt_id))
                return {'id':receipt_id}
            p=patient(c,d)
            appointment=None
            if d.get('appointment_id'):
                appointment=one(c,'SELECT * FROM appointments WHERE id=?',(d['appointment_id'],))
                if not appointment or appointment['patient_id']!=p['id']:raise ValueError('นัดหมายไม่ตรงกับผู้รับบริการ')
                if appointment['status'] in ['ยกเลิก','เสร็จสิ้น']:raise ValueError('นัดหมายนี้ยกเลิกหรือบันทึกเสร็จสิ้นแล้ว')
                if one(c,'SELECT procedure_id FROM procedure_details WHERE appointment_id=?',(appointment['id'],)):raise ValueError('นัดหมายนี้มีบันทึกหัตถการแล้ว')
            if not p['clinical_review']:raise ValueError('กรุณาทบทวนประวัติแพ้ยาและโรคประจำตัวก่อน')
            consent=one(c,"SELECT decision FROM consents WHERE patient_id=? AND purpose='การรักษา' ORDER BY id DESC LIMIT 1",(p['id'],))
            if not consent or consent['decision']!='ยินยอม':raise ValueError('ยังไม่มีความยินยอมการรักษาที่ใช้งานได้')
            if d.get('review_confirmed') is not True:raise ValueError('ต้องยืนยันว่าทบทวนประวัติและความเหมาะสมแล้ว')
            doctor=textval(d,'doctor');staff=textval(d,'staff',False);fee=number(d,'doctor_fee');commission=number(d,'commission')
            base=number(d,'commission_base');rate=number(d,'commission_rate')
            pricing=None
            if d.get('item_pricing') is True:
                from decimal import Decimal, ROUND_HALF_UP
                def cents(v):return Decimal(str(v)).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
                priced=[];subtotal=Decimal('0')
                items=d.get('items',[])
                if not isinstance(items,list) or len(items)>30:raise ValueError('รายการสินค้าไม่ถูกต้อง')
                for item in items:
                    product=one(c,'SELECT name,unit FROM products WHERE id=?',(item.get('product_id'),))
                    if not product:raise ValueError('ไม่พบผลิตภัณฑ์')
                    if 'unit_price' not in item or item['unit_price']=='':raise ValueError('กรุณาระบุราคาขายทุกรายการ')
                    qty=number(item,'qty',0.000001);price=cents(number(item,'unit_price'));total=cents(Decimal(str(qty))*price);subtotal+=total
                    priced.append({'name':product['name'],'unit':product['unit'],'qty':qty,'unit_price':float(price),'total':float(total)})
                service_fee=cents(number(d,'service_fee'));discount=cents(number(d,'discount'))
                net=subtotal+service_fee-discount
                if net<0 or net>Decimal('10000000000'):raise ValueError('ส่วนลดหรือยอดสุทธิไม่ถูกต้อง')
                base=float(net);pricing=(json.dumps(priced,ensure_ascii=False),float(subtotal),float(service_fee),float(discount),base)
            if rate>100:raise ValueError('เปอร์เซ็นต์คอมมิชชันต้องอยู่ระหว่าง 0–100')
            if 'commission_rate' in d:
                from decimal import Decimal, ROUND_HALF_UP
                commission=float((Decimal(str(base))*Decimal(str(rate))/100).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP))
            if commission and not staff:raise ValueError('ต้องระบุพนักงานผู้รับค่าคอมมิชชัน')
            eid=c.execute('INSERT INTO procedures(patient_id,service,doctor,nurse,note,created,doctor_fee,staff,commission,actor) VALUES(?,?,?,?,?,?,?,?,?,?)',(p['id'],textval(d,'service'),doctor,textval(d,'nurse',False),textval(d,'note'),now(),fee,staff,commission,u['id'])).lastrowid
            c.execute('INSERT INTO procedure_details(procedure_id,appointment_id,commission_base,commission_rate) VALUES(?,?,?,?)',(eid,appointment['id'] if appointment else None,base,rate))
            if pricing:c.execute('INSERT INTO procedure_pricing(procedure_id,items,subtotal,service_fee,discount,net) VALUES(?,?,?,?,?,?)',(eid,)+pricing)
            if appointment:c.execute("UPDATE appointments SET status='เสร็จสิ้น' WHERE id=?",(appointment['id'],))
            face=d.get('face')
            if face:
                consent=one(c,"SELECT decision FROM consents WHERE patient_id=? AND purpose='ภาพก่อน–หลัง' ORDER BY id DESC LIMIT 1",(p['id'],))
                if not consent or consent['decision']!='ยินยอม':raise ValueError('ต้องบันทึกความยินยอมสำหรับภาพก่อน–หลังก่อนบันทึกภาพใบหน้า')
                for name in ['original','simulation']:
                    value=textval(face,name,limit=1500000)
                    if not value.startswith('data:image/jpeg;base64,'):raise ValueError('รองรับภาพใบหน้า JPEG เท่านั้น')
                    try:image=base64.b64decode(value.split(',',1)[1],validate=True)
                    except:raise ValueError('ภาพใบหน้าไม่ถูกต้อง')
                    if not image.startswith(b'\xff\xd8\xff'):raise ValueError('ภาพใบหน้าไม่ถูกต้อง')
                c.execute('INSERT INTO procedure_faces(procedure_id,original,simulation,notes) VALUES(?,?,?,?)',(eid,face['original'],face['simulation'],textval(face,'notes',False,10000)))
            items=d.get('items',[])
            if not isinstance(items,list) or len(items)>30:raise ValueError('รายการสินค้าไม่ถูกต้อง')
            for item in items:
                need=number(item,'qty',0.000001)
                lots=rows(c,'SELECT * FROM lots WHERE product_id=? AND expiry>=? AND qty>0 ORDER BY expiry,id',(item.get('product_id'),today()))
                if sum(l['qty'] for l in lots)+1e-9<need:raise ValueError('สินค้า Lot ที่ใช้งานได้ไม่เพียงพอ กรุณาจัดสรร Lot ก่อน')
                for l in lots:
                    take=min(need,l['qty'])
                    if take<=0:break
                    c.execute('UPDATE lots SET qty=qty-? WHERE id=?',(take,l['id']));c.execute('INSERT INTO procedure_lots VALUES(?,?,?)',(eid,l['id'],take));c.execute('INSERT INTO movements(lot_id,qty,reason,created,actor) VALUES(?,?,?,?,?)',(l['id'],-take,'หัตถการ #'+str(eid),now(),u['id']));need-=take
        elif key=='packages':
            if action=='redeem':
                k=one(c,'SELECT * FROM packages WHERE id=?',(d.get('id'),));qty=number(d,'qty',1,True)
                if not k or k['expiry']<today() or k['remaining']<qty:raise ValueError('คอร์สหมดอายุหรือยอดคงเหลือไม่เพียงพอ')
                eid=k['id'];c.execute('UPDATE packages SET remaining=remaining-? WHERE id=?',(qty,eid));c.execute('INSERT INTO redemptions(package_id,qty,reason,created,actor) VALUES(?,?,?,?,?)',(eid,qty,textval(d,'reason'),now(),u['id']))
            elif action=='promotion':
                discount=number(d,'discount');start=validdate(textval(d,'start'));end=validdate(textval(d,'end'))
                if discount>100 or end<start:raise ValueError('ส่วนลดหรือช่วงวันที่ไม่ถูกต้อง')
                eid=c.execute('INSERT INTO promotions(name,discount,start,end,terms) VALUES(?,?,?,?,?)',(textval(d,'name'),discount,start,end,textval(d,'terms'))).lastrowid
            else:
                p=patient(c,d);total=number(d,'total',1,True);expiry=validdate(textval(d,'expiry'))
                if expiry<today():raise ValueError('คอร์สต้องยังไม่หมดอายุ')
                eid=c.execute('INSERT INTO packages(patient_id,name,total,remaining,price,expiry) VALUES(?,?,?,?,?,?)',(p['id'],textval(d,'name'),total,total,number(d,'price'),expiry)).lastrowid
        elif key=='finance':
            if action=='convert':
                f=one(c,"SELECT * FROM finance WHERE id=? AND kind='quote'",(d.get('id'),))
                if not f:raise ValueError('ไม่พบใบเสนอราคา')
                if one(c,'SELECT id FROM finance WHERE quote_id=?',(f['id'],)):raise ValueError('ใบเสนอราคานี้ออกใบเสร็จแล้ว')
                eid=c.execute('INSERT INTO finance(kind,patient_id,customer,description,amount,date,source,quote_id) VALUES(?,?,?,?,?,?,?,?)',('receipt',f['patient_id'],f['customer'],f['description'],f['amount'],today(),'ใบเสนอราคา #'+str(f['id']),f['id'])).lastrowid
            else:
                kind=textval(d,'kind')
                if kind not in ['quote','receipt','expense']:raise ValueError('ประเภทเอกสารไม่ถูกต้อง')
                if kind=='expense' and u['role']=='Front':raise PermissionError('Front ไม่มีสิทธิ์บันทึกรายจ่าย')
                pid=d.get('patient_id') or None;customer=textval(d,'customer',False)
                if pid:customer=patient(c,d)['name']
                if not customer:raise ValueError('กรุณาระบุลูกค้าหรือผู้รับเงิน')
                amount=number(d,'amount',0.01)
                eid=c.execute('INSERT INTO finance(kind,patient_id,customer,description,amount,date,source) VALUES(?,?,?,?,?,?,?)',(kind,pid,customer,textval(d,'description'),amount,validdate(textval(d,'date')),'บันทึกใน Yuna Clinic')).lastrowid
        elif key=='users':
            if action=='toggle':
                target=one(c,'SELECT * FROM users WHERE id=?',(d.get('id'),))
                if not target or target['id']==u['id']:raise ValueError('ไม่สามารถปิดบัญชีของตนเอง')
                eid=target['id'];c.execute('UPDATE users SET active=1-active WHERE id=?',(eid,));c.execute('DELETE FROM sessions WHERE user_id=?',(eid,))
            elif action=='password':
                target=one(c,'SELECT * FROM users WHERE id=?',(d.get('id'),))
                if not target:raise ValueError('ไม่พบบัญชี')
                pw=textval(d,'password')
                if len(pw)<12:raise ValueError('รหัสผ่านต้องยาวอย่างน้อย 12 ตัวอักษร')
                eid=target['id'];c.execute('UPDATE users SET password=? WHERE id=?',(hashpw(pw),eid));c.execute('DELETE FROM sessions WHERE user_id=?',(eid,))
            else:
                pw=textval(d,'password');role=textval(d,'role')
                if role not in ROLES or len(pw)<12:raise ValueError('บทบาทไม่ถูกต้องหรือรหัสผ่านสั้นกว่า 12 ตัวอักษร')
                eid=c.execute('INSERT INTO users(username,name,role,password) VALUES(?,?,?,?)',(textval(d,'username').lower(),textval(d,'name'),role,hashpw(pw))).lastrowid
        else:raise ValueError('ไม่พบคำสั่ง')
        audit(c,u,action,key,eid,detail)
        return {'ok':True,'id':eid}

if __name__=='__main__':
    init();httpd=ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
    print(f'Yuna Clinic: http://127.0.0.1:{PORT}',flush=True)
    import sys
    if '--open' in sys.argv:
        import webbrowser
        threading.Timer(.5,lambda:webbrowser.open(f'http://127.0.0.1:{PORT}')).start()
    httpd.serve_forever()
