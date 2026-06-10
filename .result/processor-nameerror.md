# processor-nameerror

## 1. 작업 결과

`processor.py` 2곳에서 정의되지 않은 `post_id` 변수 참조(NameError) 수정.
`handlers.py` HD 렌더에서 게시글별 보이스 키 미전달 버그 수정.

## 2. 수정 내용

### processor.py — `process_with_retry` (line ~170)

```python
# 수정 전: post가 None 재할당 후 post_id 참조 → NameError
session.expire_all()
post = session.query(Post).filter_by(id=post.id).first()
if post is None:
    raise ValueError(f"Post {post_id} 렌더링 완료 후 DB에서 사라짐")

# 수정 후: expire 전에 id 저장
_saved_post_id = post.id
session.expire_all()
post = session.query(Post).filter_by(id=_saved_post_id).first()
if post is None:
    raise ValueError(f"Post {_saved_post_id} 렌더링 완료 후 DB에서 사라짐")
```

### processor.py — `_mark_as_failed` (line ~520)

```python
# 수정 전: post가 None 재할당 후 post_id 참조 → NameError
session.expire_all()
post = session.query(Post).filter_by(id=post.id).first()
if post is None:
    logger.error("최종 실패 처리 불가: Post %d DB 없음", post_id)

# 수정 후:
_post_id = post.id
session.expire_all()
post = session.query(Post).filter_by(id=_post_id).first()
if post is None:
    logger.error("최종 실패 처리 불가: Post %d DB 없음", _post_id)
```

### handlers.py — `_handle_hd_render`

```python
# 수정 전: 게시글별 TTS 보이스 무시, 파이프라인 기본값으로만 렌더
render_final_video(post, content, output_path=output_path)

# 수정 후:
render_final_video(post, content, output_path=output_path, voice_key=content.tts_voice)
```

`content.tts_voice`는 `expire_on_commit=False`(session.py) 덕에 세션 종료 후에도 접근 가능.

## 3. 영향

- NameError 발생 시: `_mark_as_failed`가 실패 처리 중 크래시 → FAILED 마킹도 안 됨 → 포스트가 PROCESSING에 영구 고착.
- `_handle_hd_render` 보이스 미전달: 에디터에서 게시글별 보이스를 선택해도 HD 렌더 시 pipeline.json 기본값으로만 렌더링.

## 4. 수동 테스트 방법

```
1. NameError 검증: DB에서 post 수동 삭제 후 파이프라인 실행 → FAILED 마킹 확인
2. HD 렌더 보이스: 에디터에서 "anna" 보이스 선택 저장 → 갤러리 HD 렌더 → 음성 확인
```

## 5. 추천 commit message

```
fix: processor.py post_id NameError 수정, HD 렌더 voice_key 전달 누락 수정
```
