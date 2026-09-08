-- PostgreSQL schema. Apply once with python manage.py init-db.

CREATE TABLE IF NOT EXISTS users(id BIGSERIAL PRIMARY KEY,username TEXT UNIQUE NOT NULL,name TEXT NOT NULL,role TEXT NOT NULL,password TEXT NOT NULL,active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id),csrf TEXT NOT NULL,created DOUBLE PRECISION,last_seen DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS patients(id BIGSERIAL PRIMARY KEY,hn TEXT UNIQUE,name TEXT,nickname TEXT,age INTEGER,phone TEXT,address TEXT,emergency TEXT,conditions TEXT,allergies TEXT,medicines TEXT,clinical_review INTEGER DEFAULT 0,member TEXT DEFAULT 'Standard');
CREATE TABLE IF NOT EXISTS consents(id BIGSERIAL PRIMARY KEY,patient_id INTEGER REFERENCES patients(id),purpose TEXT,version TEXT,decision TEXT,signed_by TEXT,created TEXT,actor INTEGER REFERENCES users(id));
CREATE TABLE IF NOT EXISTS photos(id BIGSERIAL PRIMARY KEY,patient_id INTEGER REFERENCES patients(id),phase TEXT,note TEXT,mime TEXT,image BYTEA,created TEXT,actor INTEGER REFERENCES users(id));
CREATE TABLE IF NOT EXISTS appointments(id BIGSERIAL PRIMARY KEY,patient_id INTEGER REFERENCES patients(id),service TEXT,doctor TEXT,room TEXT,start TEXT,duration INTEGER,status TEXT DEFAULT 'รอยืนยัน',followup TEXT,followup_note TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS products(id BIGSERIAL PRIMARY KEY,code TEXT UNIQUE,name TEXT,category TEXT,unit TEXT,opening DOUBLE PRECISION DEFAULT 0,min_stock DOUBLE PRECISION DEFAULT 5);
CREATE TABLE IF NOT EXISTS lots(id BIGSERIAL PRIMARY KEY,product_id INTEGER REFERENCES products(id),lot TEXT,expiry TEXT,qty DOUBLE PRECISION,cost DOUBLE PRECISION,UNIQUE(product_id,lot));
CREATE TABLE IF NOT EXISTS movements(id BIGSERIAL PRIMARY KEY,lot_id INTEGER REFERENCES lots(id),qty DOUBLE PRECISION,reason TEXT,created TEXT,actor INTEGER REFERENCES users(id));
CREATE TABLE IF NOT EXISTS procedures(id BIGSERIAL PRIMARY KEY,patient_id INTEGER REFERENCES patients(id),service TEXT,doctor TEXT,nurse TEXT,note TEXT,created TEXT,doctor_fee DOUBLE PRECISION,staff TEXT,commission DOUBLE PRECISION,actor INTEGER REFERENCES users(id));
CREATE TABLE IF NOT EXISTS procedure_lots(procedure_id INTEGER REFERENCES procedures(id),lot_id INTEGER REFERENCES lots(id),qty DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS packages(id BIGSERIAL PRIMARY KEY,patient_id INTEGER REFERENCES patients(id),name TEXT,total INTEGER,remaining INTEGER,price DOUBLE PRECISION,expiry TEXT);
CREATE TABLE IF NOT EXISTS redemptions(id BIGSERIAL PRIMARY KEY,package_id INTEGER REFERENCES packages(id),qty INTEGER,reason TEXT,created TEXT,actor INTEGER REFERENCES users(id));
CREATE TABLE IF NOT EXISTS promotions(id BIGSERIAL PRIMARY KEY,name TEXT,discount DOUBLE PRECISION,start TEXT,"end" TEXT,terms TEXT);
CREATE TABLE IF NOT EXISTS finance(id BIGSERIAL PRIMARY KEY,kind TEXT,patient_id INTEGER REFERENCES patients(id),customer TEXT,description TEXT,amount DOUBLE PRECISION,source_profit DOUBLE PRECISION,date TEXT,source TEXT,quote_id INTEGER UNIQUE REFERENCES finance(id));
CREATE TABLE IF NOT EXISTS audit(id BIGSERIAL PRIMARY KEY,created TEXT,user_id INTEGER,actor TEXT,action TEXT,entity TEXT,entity_id TEXT,detail TEXT);
CREATE TABLE IF NOT EXISTS source_meta(key TEXT PRIMARY KEY,value TEXT);
CREATE TABLE IF NOT EXISTS login_attempts(id BIGSERIAL PRIMARY KEY,key TEXT NOT NULL,created DOUBLE PRECISION NOT NULL);
CREATE INDEX IF NOT EXISTS login_attempts_lookup ON login_attempts(key,created);
CREATE TABLE IF NOT EXISTS procedure_faces(procedure_id BIGINT PRIMARY KEY REFERENCES procedures(id),original TEXT NOT NULL,simulation TEXT NOT NULL,notes TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS procedure_details(procedure_id BIGINT PRIMARY KEY REFERENCES procedures(id),appointment_id BIGINT UNIQUE REFERENCES appointments(id),commission_base DOUBLE PRECISION NOT NULL DEFAULT 0,commission_rate DOUBLE PRECISION NOT NULL DEFAULT 0);
