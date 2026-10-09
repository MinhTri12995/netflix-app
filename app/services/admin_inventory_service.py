"""Bounded database reads for admin views; production errors never use local data."""
import json
import math
import database as db

ACCOUNT_COLUMNS = 'email,expire_date,netflix_id,secure_netflix_id,created_at,plan,status'
KEY_COLUMNS = 'code,assigned_email,created_at,expire_at,plan'
STATUSES = ('live','usable','needs_review','dead','expired','blocked_for_new_assignments')


def inventory_page(kind, page=1, per_page=50, search='', status='', plan=''):
    if kind not in ('accounts','codes'):
        raise ValueError('Invalid inventory kind')
    try:
        page = max(1,int(page))
    except (ValueError,TypeError):
        page = 1
    per_page = min(100,max(1,int(per_page)))
    table = 'netflix_accounts' if kind == 'accounts' else 'access_keys'
    field = 'email' if kind == 'accounts' else 'code'
    columns = ACCOUNT_COLUMNS if kind == 'accounts' else KEY_COLUMNS
    if db.SUPABASE_KEY:
        query = db.get_supabase().table(table).select(columns,count='exact')
        if search:
            query = query.ilike(field,'%'+search.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%')
        if status in STATUSES and kind == 'accounts':
            query = query.eq('status',status)
        if plan:
            query = query.eq('plan',plan)
        # Ordering includes a unique tie breaker for stable page boundaries.
        response = query.order('created_at',desc=True).order(field).range((page-1)*per_page,page*per_page-1).execute()
        total = response.count or 0
        pages = max(1,math.ceil(total/per_page))
        if page > pages:
            return inventory_page(kind,pages,per_page,search,status,plan)
        rows = [tuple(row.get(key) for key in columns.split(',')) for row in response.data or []]
    else:
        conn = db.get_sqlite_conn()
        try:
            conditions, args = [], []
            if search:
                conditions.append(f'{field} LIKE ? ESCAPE \'\\\'')
                args.append('%'+search.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%')
            if status in STATUSES and kind == 'accounts':
                conditions.append('status=?'); args.append(status)
            if plan:
                conditions.append('plan=?'); args.append(plan)
            where = ' WHERE '+' AND '.join(conditions) if conditions else ''
            total = conn.execute(f'SELECT COUNT(*) FROM {table}{where}',args).fetchone()[0]
            pages = max(1,math.ceil(total/per_page))
            page = min(page,pages)
            rows = conn.execute(f'SELECT {columns} FROM {table}{where} ORDER BY created_at DESC,{field} LIMIT ? OFFSET ?',[*args,per_page,(page-1)*per_page]).fetchall()
        finally:
            conn.close()
    return {'rows':rows,'total':total,'page':page,'pages':pages}


def inventory_summary():
    if db.SUPABASE_KEY:
        return db.get_supabase().rpc('admin_inventory_summary',{}).execute().data
    conn = db.get_sqlite_conn()
    try:
        stats = {'accounts':dict.fromkeys(('total','Premium','Standard','Standard_Ads','Basic'),0),
                 'codes':dict.fromkeys(('total','Premium','Standard','Standard_Ads','Basic'),0),
                 'health':dict.fromkeys((*STATUSES,'unknown','dangling'),0)}
        for table,key in [('netflix_accounts','accounts'),('access_keys','codes')]:
            for plan,count in conn.execute(f'SELECT plan,COUNT(*) FROM {table} GROUP BY plan'):
                stats[key]['total'] += count
                normalized = 'Standard_Ads' if plan == 'Standard with Ads' else plan
                if normalized in stats[key]:
                    stats[key][normalized] += count
        for status,count in conn.execute('SELECT status,COUNT(*) FROM netflix_accounts GROUP BY status'):
            stats['health'][status if status in STATUSES else 'unknown'] += count
        stats['health']['dangling'] = conn.execute('SELECT COUNT(*) FROM access_keys k LEFT JOIN netflix_accounts a ON a.email=k.assigned_email WHERE a.email IS NULL').fetchone()[0]
        return stats
    finally:
        conn.close()


def account_details(email):
    if db.SUPABASE_KEY:
        codes = db.get_supabase().table('access_keys').select('code').eq('assigned_email',email).order('code').limit(100).execute().data
        literal = json.dumps(email)
        events = db.get_supabase().table('events_outbox').select('event_type,payload,created_at').or_('payload->>old_email.eq.'+literal+',payload->>new_email.eq.'+literal).order('created_at',desc=True).limit(20).execute().data
    else:
        conn = db.get_sqlite_conn()
        try:
            codes = [{'code':row[0]} for row in conn.execute('SELECT code FROM access_keys WHERE assigned_email=? ORDER BY code LIMIT 100',(email,))]
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='events_outbox'").fetchone()
            events = [{'event_type':r[0],'payload':json.loads(r[1]),'created_at':r[2]} for r in conn.execute("SELECT event_type,payload,created_at FROM events_outbox WHERE json_extract(payload,'$.old_email')=? OR json_extract(payload,'$.new_email')=? ORDER BY id DESC LIMIT 20",(email,email))] if exists else []
        finally:
            conn.close()
    # Do not return arbitrary event payloads or cookies to this view.
    return {'codes':[r['code'] for r in codes or []], 'events':[
        {'type':r['event_type'],'created_at':r['created_at'], 'actor':(r.get('payload') or {}).get('actor',''),
         'code':(r.get('payload') or {}).get('code','')} for r in events or []]}
