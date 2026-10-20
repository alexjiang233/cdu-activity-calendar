"""重建搜索与月份索引。后台改完内容、或迁移之后跑一次。"""
from django.core.management.base import BaseCommand

from catalog.indexing import refresh_all


class Command(BaseCommand):
    help = '重建通知/活动的可检索文本与往年月份索引'

    def handle(self, *args, **options):
        stats = refresh_all()
        self.stdout.write(self.style.SUCCESS(
            f"索引已重建：通知 {stats['notices']} 条，活动 {stats['activities']} 条"))
