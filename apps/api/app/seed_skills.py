"""Seed bốn kỹ năng nghiệp vụ mẫu, chạy được nhiều lần và độc lập với seed_demo.

Vì sao tách ra thành lệnh riêng: `seed_demo` chỉ chạy **một lần** trên máy chủ, canh bằng một tệp
marker, nên thêm kỹ năng vào đó sẽ không bao giờ tới được bản deploy đã seed từ trước. Lệnh này
chạy mỗi lần deploy, giống `seed_ops`, và chỉ tạo cái còn thiếu.

    cd apps/api && .venv/bin/python -m app.seed_skills

Nó không đè lên kỹ năng quản trị viên đã sửa: kỹ năng đã tồn tại theo mã thì chỉ được bổ sung
những liên kết còn thiếu, không ghi lại nội dung.
"""

import asyncio

from sqlalchemy import select

from app.db import async_session_factory
from app.models import App, Dataset, Workspace
from app.seed_demo import DATASETS, SKILLS, seed_skills


async def main() -> None:
    print("Seed kỹ năng nghiệp vụ…")
    async with async_session_factory() as db:
        units_needed = {spec["unit"] for spec in SKILLS}
        # `seed_demo.UNITS` gắn khoá ngắn với tên đơn vị; lấy lại đúng ánh xạ đó từ danh sách kho.
        from app.seed_demo import UNITS

        by_key = {u["key"]: u["name"] for u in UNITS}
        units: dict[str, Workspace] = {}
        for key in units_needed:
            name = by_key.get(key)
            ws = (await db.execute(select(Workspace).where(Workspace.name == name))).scalar_one_or_none()
            if ws is None:
                print(f"  ! chưa có đơn vị '{name}', bỏ qua kỹ năng của {key}")
                continue
            units[key] = ws

        datasets: dict[str, Dataset] = {}
        for spec in DATASETS:
            ws = units.get(spec["unit"])
            if ws is None:
                continue
            ds = (await db.execute(select(Dataset).where(
                Dataset.workspace_id == ws.id, Dataset.name == spec["name"]))).scalar_one_or_none()
            if ds is not None:
                datasets[spec["key"]] = ds

        wanted_apps = {name for spec in SKILLS for name in spec.get("apps", [])}
        apps = (await db.execute(select(App).where(App.name.in_(wanted_apps)))).scalars().all()

        if not units:
            print("  ! chưa có đơn vị nào, cần chạy `python -m app.seed_demo` trước")
            return

        made = await seed_skills(db, units, datasets, apps)
        print(f"\nXong. {len(made)} kỹ năng sẵn sàng: {', '.join(sorted(made))}")


if __name__ == "__main__":
    asyncio.run(main())
