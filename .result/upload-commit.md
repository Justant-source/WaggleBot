# upload-commit

## 1. 작업 결과

`_handle_upload` 핸들러에서 업로드 결과가 DB에 영구 저장되지 않는 버그 수정.
- `upload_meta`(YouTube video_id/URL 포함) 미저장 → 재업로드 시 동영상 중복 생성 가능
- `post.status` UPLOADED 미전환 → 갤러리에서 업로드 완료 포스트가 RENDERED로 계속 표시

## 2. 수정 내용

### handlers.py — `_handle_upload`

```python
# 수정 전: upload_post()가 session.flush()만 호출하고 핸들러가 commit 없이 with 블록 탈출
# → session.close() = implicit rollback → upload_meta 손실, status 미갱신
with SessionLocal() as db:
    post = db.query(Post).filter_by(id=post_id).first()
    content = db.query(Content).filter_by(post_id=post_id).first()
    result = upload_post(post, content, db, target_platform=platform)
# ← db.commit() 없음, db.close() = rollback

# 수정 후: 업로드 성공 시 status 갱신 + commit으로 upload_meta 영속화
from db.models import Post, Content, PostStatus

with SessionLocal() as db:
    post = db.query(Post).filter_by(id=post_id).first()
    content = db.query(Content).filter_by(post_id=post_id).first()
    result = upload_post(post, content, db, target_platform=platform)
    if result:
        post.status = PostStatus.UPLOADED
    db.commit()
```

### 참고: main.py `upload_once()`는 이미 올바름

자동 업로드 경로(`auto_upload=true` 시 ai_worker 내 `upload_once()`)는 이미
`session.commit()` + `post.status = PostStatus.UPLOADED` 처리가 있어 정상.
버그는 UI에서 갤러리 업로드 버튼을 누를 때만 실행되는 `_handle_upload`에만 존재.

## 3. 영향

- `upload_meta` 미저장: YouTube 업로드는 성공하지만 DB에 video_id/URL이 없어
  다음 번 업로드 시 중복 동영상이 생성되고, Analytics 수집도 불가(video_id 없음)
- `post.status` 미갱신: 갤러리 페이지에서 RENDERED 상태로 계속 표시
  (업로드 버튼이 사라지지 않고 계속 표시됨)

## 4. 수동 테스트 방법

```
1. 갤러리에서 RENDERED 포스트의 업로드 버튼 클릭
2. Job 완료 후 DB 확인:
   SELECT status, upload_meta FROM posts WHERE id = <post_id>;
   → status = 'UPLOADED', upload_meta에 youtube.video_id 존재 확인
3. 다시 업로드 버튼 클릭 시 "이미 업로드됨" 로그만 찍히고 중복 업로드 없음 확인
```

## 5. 추천 commit message

```
fix: _handle_upload upload_meta 미저장 버그 수정 (commit 누락 + UPLOADED 상태 갱신)
```
