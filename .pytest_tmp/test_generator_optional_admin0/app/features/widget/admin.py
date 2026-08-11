"""
Widget domain SQLAdmin views.

컨벤션: 모듈 레벨 ``admin_views`` 리스트를 패키지 ``__init__.py`` 가 재노출하면
main.py 가 SQLAdmin 에 등록한다.

활성화하려면 placeholder 를 실제 모델 기반 ModelView 로 교체한다:
    from sqladmin import ModelView
    from app.features.widget.models.models import WidgetModel

    class WidgetAdmin(ModelView, model=WidgetModel):
        column_list = "__all__"

    admin_views = [WidgetAdmin]
"""

# 아직 등록된 뷰 없음 — 위에 ModelView 를 추가하고 admin_views 에 넣으세요.
admin_views: list[type] = []
