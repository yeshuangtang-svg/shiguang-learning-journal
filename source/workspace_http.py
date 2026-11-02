"""HTTP routes for learning workspace features; shares the main access policy."""
import re
from urllib.parse import unquote
from backups import MAX_ARCHIVE
from pdf_export import generate_pdf


def dispatch_workspace(h,path,q):
    app=h.app; store=app.store; method=h.command
    def send(result,status=200): h.send_json(result,status); return True
    if path=='/api/search' and method=='GET':
        return send(store.search_all(q.get('query',''),q.get('kind'),int(q.get('limit',20)),int(q.get('offset',0))))
    if path=='/api/entries-page' and method=='GET':
        args={k:v for k,v in q.items() if k in ('date_from','date_to','subject','query')}; args.update(limit=int(q.get('limit',20)),offset=int(q.get('offset',0)))
        return send(store.entries_page(**args))
    if path=='/api/links':
        if method=='GET': return send({'items':store.links_for(q.get('kind'),q.get('id'))})
        if method=='POST': return send(store.add_link(h.body()),201)
    if re.fullmatch('/api/links/[a-f0-9]{32}',path) and method=='DELETE': return send({'deleted':store.remove_link(path.rsplit('/',1)[1])})
    if path=='/api/linked-notes' and method=='POST':
        body=h.body(); result=store.create_linked_note(body.get('origin_kind'),body.get('origin_id'),body.get('kind'),body.get('data'))
        if body['kind']=='document': result=app.document_files.sync_after_save(result)
        return send(result,201)
    if path=='/api/trash' and method=='GET': return send({'items':store.list_trash()})
    if re.fullmatch('/api/trash/[a-f0-9]{32}/restore',path) and method=='POST':
        h.body(); return send(store.restore_trash(path.split('/')[-2]))
    if path=='/api/drafts' and method=='GET': return send({'items':store.list_drafts()})
    if path.startswith('/api/drafts/'):
        key=unquote(path[len('/api/drafts/'):])
        if method=='POST': return send(store.save_draft(key,h.body()))
        if method=='DELETE': return send(store.delete_draft(key))
    match=re.fullmatch('/api/documents/([a-f0-9]{32})/(position|history|generate-pdf)(?:/([a-f0-9]{64}))?',path)
    if match:
        identity,action,version=match.groups()
        if action=='position':
            if method=='GET': return send(store.reading_position(identity))
            if method=='POST': return send(store.reading_position(identity,h.body()))
        if action=='history' and method=='GET':
            if version:
                data,mime,name=app.document_files.history_content(identity,version); h.send_file(data,mime,name); return True
            return send({'items':app.document_files.history(identity)})
        if action=='generate-pdf' and method=='POST':
            h.body()
            from server import ROOT
            return send(generate_pdf(app.document_files,identity,ROOT/'static'))
    if path=='/api/backups':
        if method=='GET': return send({'items':app.backups.list()})
        if method=='POST': return send(app.backups.create(h.body().get('include_config',False)),201)
    if re.fullmatch('/api/backups/[a-f0-9]{32}/download',path) and method=='GET':
        identity=path.split('/')[-2]; target=app.backups.archive_path(identity)
        if not target.is_file(): raise KeyError('备份不存在。')
        h.send_file(target.read_bytes(),'application/zip','Shiguang-backup-'+identity[:8]+'.zip'); return True
    if path=='/api/backups/preview' and method=='POST':
        length=int(h.headers.get('Content-Length',0))
        if not 0<length<=MAX_ARCHIVE: raise ValueError('备份为空或超过 512 MiB。')
        return send(app.backups.preview(h.rfile.read(length)))
    if path=='/api/backups/restore' and method=='POST':
        body=h.body(); return send(app.backups.restore(body.get('token'),body.get('restore_config',False)))
    return False
