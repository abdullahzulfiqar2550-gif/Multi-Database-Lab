import time
import streamlit as st
import pandas as pd

st.set_page_config(page_title="DB Lab", layout="wide")
st.title("Database Lab")

@st.cache_resource
def get_mysql():
    import mysql.connector
    for _ in range(15):
        try: return mysql.connector.connect(host="mysql", user="root", password="root123")
        except: time.sleep(3)

@st.cache_resource
def get_postgres():
    import psycopg2
    for _ in range(15):
        try:
            con = psycopg2.connect(host="postgres", user="postgres", password="postgres123", dbname="postgres")
            con.autocommit = True
            return con
        except: time.sleep(3)

@st.cache_resource
def get_mongo():
    from pymongo import MongoClient
    for _ in range(15):
        try:
            c = MongoClient("mongodb://mongo:27017/", serverSelectionTimeoutMS=3000)
            c.server_info()
            return c
        except: time.sleep(3)

@st.cache_resource
def get_cassandra():
    from cassandra.cluster import Cluster
    for _ in range(15):
        try: return Cluster(["cassandra"]).connect()
        except: time.sleep(3)


tab_mysql, tab_pg, tab_mongo, tab_cass = st.tabs(["🐬 MySQL", "🐘 PostgreSQL", "🍃 MongoDB", "⚡ Cassandra"])


with tab_mysql:
    con = get_mysql()
    try:
        cur = con.cursor()
        cur.execute("SHOW DATABASES")
        dbs = [r[0] for r in cur.fetchall() if r[0] not in ("information_schema","performance_schema","mysql","sys")]
        cur.close()
        for db in dbs:
            cur = con.cursor()
            cur.execute(f"SHOW TABLES FROM `{db}`")
            tbls = [r[0] for r in cur.fetchall()]
            cur.close()
            st.markdown(f"**{db}:** " + (", ".join(f"`{t}`" for t in tbls) if tbls else "*(no tables)*"))
    except: pass

    query = st.text_area("SQL Query", height=160, key="mysql_q")
    if st.button("Execute", key="mysql_exec", use_container_width=True):
        try:
            cur = con.cursor()
            cur.execute(query.strip())
            if query.strip().upper().startswith(("SELECT", "SHOW")):
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]
                cur.close()
                st.success("Executed successfully")
                st.dataframe(pd.DataFrame(rows, columns=cols), use_container_width=True)
            else:
                con.commit()
                cur.close()
                st.success(f"Executed successfully. Rows affected: {cur.rowcount}")
        except Exception as e:
            st.error(e)


with tab_pg:
    pg = get_postgres()
    try:
        cur = pg.cursor()
        cur.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema') ORDER BY table_schema, table_name")
        for schema, tbl in cur.fetchall():
            st.markdown(f"**{schema}:** `{tbl}`")
        cur.close()
    except: pass

    query = st.text_area("SQL Query", height=160, key="pg_q")
    if st.button("Execute", key="pg_exec", use_container_width=True):
        try:
            cur = pg.cursor()
            cur.execute(query.strip())
            if query.strip().upper().startswith("SELECT"):
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]
                cur.close()
                st.success("Executed successfully.")
                st.dataframe(pd.DataFrame(rows, columns=cols), use_container_width=True)
            else:
                cur.close()
                st.success("Executed successfully.")
        except Exception as e:
            st.error(e)


with tab_mongo:
    client = get_mongo()
    try:
        dbs = [d for d in client.list_database_names() if d not in ("admin","local","config")]
        for db in dbs:
            cols = client[db].list_collection_names()
            st.markdown(f"**{db}:** " + (", ".join(f"`{c}`" for c in cols) if cols else "*(no collections)*"))
    except: pass

    db_name = st.text_input("Database", value="mydb", key="mongo_db")
    query   = st.text_area("MongoDB Query", height=160, key="mongo_q",
                            placeholder='db.students.insertOne({name:"Alice", age:21})')

    if st.button("Execute", key="mongo_exec", use_container_width=True):
        try:
            import re, json
            from bson import json_util

            q = query.strip()
            if re.match(r'^use\s+\w+$', q):
                db_name = q.split()[1]
                st.success(f"Switched to database: {db_name}")
                st.stop()

            m = re.match(r'^db\.createCollection\(["\'](\w+)["\']\)$', q)
            if m:
                client[db_name].create_collection(m.group(1))
                st.success(f"Collection '{m.group(1)}' created.")
                st.stop()

            m = re.match(r'^db\.(\w+)\.(\w+)\((.*)\)$', q, re.DOTALL)
            if not m:
                st.error("Query format not recognised. Use: db.collection.operation({...})")
                st.stop()

            col_name, op, raw = m.group(1), m.group(2), m.group(3).strip()
            col = client[db_name][col_name]

            def to_json(s):
                s = re.sub(r'(\w+)\s*:', r'"\1":', s)  
                s = re.sub(r'"(\w+)"\s*:', r'"\1":', s) 
                return json.loads(s) if s else {}

            if op == "insertOne":
                r = col.insert_one(to_json(raw))
                st.success(f"Inserted. _id: {r.inserted_id}")

            elif op == "insertMany":
                docs = json.loads(raw)
                r = col.insert_many(docs)
                st.success(f"Inserted {len(r.inserted_ids)} documents")

            elif op == "find":
                parts = [p.strip() for p in raw.split(",", 1)] if raw else []
                f   = to_json(parts[0]) if len(parts) > 0 and parts[0] else {}
                prj = to_json(parts[1]) if len(parts) > 1 and parts[1] else None
                docs = list(col.find(f, prj))
                for d in docs: d["_id"] = str(d["_id"])
                st.success(f"{len(docs)} document(s) found.")
                if docs: st.dataframe(pd.DataFrame(docs), use_container_width=True)

            elif op == "findOne":
                doc = col.find_one(to_json(raw))
                if doc:
                    doc["_id"] = str(doc["_id"])
                    st.success("Document found")
                    st.json(doc)
                else:
                    st.info("No document found")

            elif op == "updateOne":
                parts = raw.split(",", 1)
                r = col.update_one(to_json(parts[0]), to_json(parts[1]))
                st.success(f"Matched: {r.matched_count}  Modified: {r.modified_count}")

            elif op == "updateMany":
                parts = raw.split(",", 1)
                r = col.update_many(to_json(parts[0]), to_json(parts[1]))
                st.success(f"Matched: {r.matched_count}  Modified: {r.modified_count}")

            elif op == "deleteOne":
                r = col.delete_one(to_json(raw))
                st.success(f"Deleted {r.deleted_count} document.")

            elif op == "deleteMany":
                r = col.delete_many(to_json(raw))
                st.success(f"Deleted {r.deleted_count} documents.")

            elif op == "drop":
                col.drop()
                st.success(f"Collection '{col_name}' dropped.")

            elif op == "countDocuments":
                n = col.count_documents(to_json(raw))
                st.success(f"Count: {n}")

            else:
                st.error(f"Operation '{op}' is not supported via this interface.")

        except Exception as e:
            st.error(e)


with tab_cass:
    session = get_cassandra()
    try:
        ks_rows   = session.execute("SELECT keyspace_name FROM system_schema.keyspaces")
        keyspaces = [r.keyspace_name for r in ks_rows if not r.keyspace_name.startswith("system")]
        for ks in keyspaces:
            tbls = [r.table_name for r in session.execute("SELECT table_name FROM system_schema.tables WHERE keyspace_name=%s", [ks])]
            st.markdown(f"**{ks}:** " + (", ".join(f"`{t}`" for t in tbls) if tbls else "*(no tables)*"))
    except: pass

    query = st.text_area("CQL Query", height=160, key="cass_q")
    if st.button("Execute", key="cass_exec", use_container_width=True):
        try:
            result = session.execute(query.strip())
            st.success("Executed successfully.")
            rows = list(result)
            if rows:
                st.dataframe(pd.DataFrame(rows, columns=result.column_names), use_container_width=True)
        except Exception as e:
            st.error(e)