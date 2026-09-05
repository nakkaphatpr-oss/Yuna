# Yuna Clinic — GitHub / Vercel

Repository: `https://github.com/nakkaphatpr-oss/Yuna`

Vercel project: `yunachatgptversion` ในทีม `nakkaphatpr-4431`

## โครงสร้าง

- `app.py`: Flask entrypoint ที่ Vercel ตรวจพบ
- `server.py`: API สิทธิ์ เซสชัน และกระบวนการคลินิก
- `database.py`: PostgreSQL สำหรับออนไลน์ / SQLite สำหรับในเครื่อง
- `public/`: HTML, CSS, JavaScript เดิม
- `schema.postgres.sql`: โครงสร้างฐานข้อมูลออนไลน์
- `.github/workflows/test.yml`: ทดสอบด้วย PostgreSQL ชั่วคราวบน GitHub Actions

ภาพก่อน–หลังเก็บเป็น BYTEA ใน PostgreSQL และต้องเปิดผ่าน API ที่ตรวจสิทธิ์ จำกัดภาพ 2.5 MB เพื่อให้คำขอ Base64 อยู่ภายในขนาดที่ Vercel รองรับ

## ส่งโค้ดขึ้น GitHub

อัปโหลดเฉพาะไฟล์โค้ดและคู่มือ ห้ามอัปโหลด `data/`, `.env`, Excel, ภาพผู้รับบริการ หรือ ZIP ชุดเดิมที่มีฐานข้อมูล โค้ดมี `.gitignore` และ `.vercelignore` กันไฟล์เหล่านี้ไว้แล้ว

หาก Git บนเครื่องเข้าสู่ระบบแล้ว ใช้ `git remote add origin https://github.com/nakkaphatpr-oss/Yuna.git` แล้ว `git push -u origin main` ตรวจ remote เดิมก่อนเพิ่ม และห้าม force push ทับงานอื่น

## เตรียมฐานข้อมูล

สร้าง PostgreSQL แยกสำหรับโปรเจกต์นี้ เช่น Neon ผ่าน Vercel Storage ตรวจสอบราคาและข้อตกลงก่อนยืนยัน จากนั้นรัน `schema.postgres.sql` ใน SQL Editor ของฐานข้อมูล หรือใช้คำสั่งต่อไปนี้บนเครื่องที่ตั้ง Environment Variable `DATABASE_URL` แล้ว:

```sh
pip install -r requirements.txt
python manage.py init-db
```

คำสั่งสร้างตารางที่ยังไม่มี โดยไม่ลบข้อมูลเดิม ไม่รัน migration บนฐานข้อมูล Production ระหว่าง Build ของ Vercel

## ตั้งค่า Vercel

ใช้โปรเจกต์เดิม `yunachatgptversion` ที่เชื่อม repository นี้ Root Directory เป็นราก repository และ Framework Preset เป็น **Flask** ใช้ค่า Build/Output เริ่มต้น อย่าตั้ง Output Directory เป็น `public` เพราะเว็บต้องมี API

ตั้ง Environment Variables ในหน้า Settings:

| ตัวแปร | ค่า |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string ของฐานข้อมูลเฉพาะโปรเจกต์ |
| `APP_ORIGIN` | URL HTTPS จริงของเว็บ ไม่มี / ท้าย URL |
| `YUNA_SETUP_TOKEN` | รหัสสุ่มอย่างน้อย 32 ตัวอักษรสำหรับสร้าง Owner ครั้งแรก |

สร้างรหัสตั้งค่าบนเครื่องด้วย `python -c "import secrets; print(secrets.token_urlsafe(32))"` แล้วเก็บใน Environment Variables เท่านั้น ห้ามใส่ใน Git หรือ URL

กำหนดฐานข้อมูล Preview แยกจาก Production หากเปิดใช้ Preview โค้ดรองรับโดเมน Preview จาก `VERCEL_URL` ที่ Vercel กำหนดให้อัตโนมัติ

จากนั้น Deploy หรือ Redeploy หลังเปลี่ยน Environment Variables การ Build สำเร็จยังไม่ได้แปลว่าฐานข้อมูลพร้อม ต้องเปิดเว็บแล้วตรวจการเชื่อมต่อด้วย

## สร้าง Owner

เปิดเว็บที่ Deploy สำเร็จ กรอกบัญชีและรหัสตั้งค่า `YUNA_SETUP_TOKEN` เพื่อสร้าง Owner จากนั้นลบตัวแปรนี้และ Redeploy บัญชีที่สร้างแล้วจะยังใช้งานได้

ข้อมูลผู้รับบริการจากเครื่องไม่ถูกส่งขึ้นออนไลน์อัตโนมัติ หากจะย้ายข้อมูล ต้องทำผ่านช่องทางฐานข้อมูลที่จำกัดสิทธิ์ ไม่ผ่าน repository สาธารณะ

## การทดสอบ

```sh
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

ค่าเริ่มต้นใช้ข้อมูลสังเคราะห์ใน SQLite ชั่วคราว หากตั้ง `TEST_DATABASE_URL` จะทดสอบกับ PostgreSQL แทน ต้องเป็นฐานข้อมูลทดสอบว่างเท่านั้น GitHub Actions มี PostgreSQL ชั่วคราวให้อยู่แล้ว

ทดสอบ Login, Secure Cookie, การกันสร้าง Owner โดยไม่มีรหัสตั้งค่า, สิทธิ์ทุกบทบาท, Consent, FEFO, การย้อนกลับธุรกรรม, นัดทับซ้อน, คอร์ส และการออกใบเสร็จซ้ำ โค้ดใช้ transaction lock ที่ฐานข้อมูลเพื่อกันรายการชนกันข้าม worker เหมาะกับคลินิกขนาดเล็ก

Vercel ไม่รอผล GitHub Actions โดยอัตโนมัติ ควรตรวจทั้งผลทดสอบและ Deployment ก่อนนำไปใช้งานจริง

## สิ่งที่คลินิกต้องดูแล

การสำรองและกู้คืน PostgreSQL, ระยะเวลาเก็บข้อมูล, สิทธิ์ทีมงานใน Vercel/GitHub และนโยบายข้อมูลของคลินิกยังต้องกำหนดเพิ่มเติม ระบบนี้ไม่ใช่การรับรอง PDPA หรือระบบบัญชีเต็มรูปแบบ
