# Django 개발환경 세팅

## postgreSQL

1. psql postgres로 접속 (초기접속시 패스워드는 필요없음)
2. postgres(root)계정 패스워드 설정

```sql
alter user postgres with password 'password'
```
	pg_hba.conf 파일 localhost trust부분을 md5로 수정
3. user 생성
```sql
CREATE USER dongkseo WITH PASSWORD 'password' CREATEDB
```
4. DB 생성 
```sql
CREATE DATABASE 'DBNAME' ENCODING 'UTF-8' OWNER dongkseo
```
5. user에 권한 부여
```sql
GRANT CONNECT ON DATABASE transecendence TO dongkseo;
```