"""plan limits: registros por formato, free 15mb, starter 6 presets

Revision ID: b1c2d3e4f5a6
Revises: 84ca83d04bf3
Create Date: 2026-08-18

Por que este cambio:

JSON pesa ~2.4x mas que CSV para el mismo numero de registros (medido:
2M registros = 121.96 MB en CSV vs 291.77 MB en JSON). Con un solo limite
de registros y un tope unico de 150 MB, un JSON al limite de registros NO
cabia en el limite de tamano — se prometia algo que el backend rechazaba.

`max_records_per_file` pasa a significar CSV; `max_records_json` es nuevo.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "84ca83d04bf3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default temporal: la tabla ya tiene filas y la columna es NOT NULL.
    op.add_column(
        "plan_limits",
        sa.Column(
            "max_records_json",
            sa.Integer(),
            nullable=False,
            server_default="100000",
        ),
    )

    # FREE: 15 MB permite ~245k registros CSV y ~102k JSON.
    op.execute(
        """
        UPDATE plan_limits
        SET max_file_size_mb = 15,
            max_records_per_file = 200000,
            max_records_json = 100000
        WHERE plan = 'FREE'
        """
    )

    # STARTER: 150 MB permite ~2.4M registros CSV y ~1M JSON.
    # num_presets sube a 6: el sexto preset (dedupe por campo) ya existe.
    op.execute(
        """
        UPDATE plan_limits
        SET max_records_per_file = 2000000,
            max_records_json = 1000000,
            num_presets = 6
        WHERE plan = 'STARTER'
        """
    )

    # El default ya cumplio su proposito; que las filas nuevas lo declaren.
    op.alter_column("plan_limits", "max_records_json", server_default=None)


def downgrade() -> None:
    op.drop_column("plan_limits", "max_records_json")

    op.execute(
        """
        UPDATE plan_limits
        SET max_file_size_mb = 10,
            max_records_per_file = 200000
        WHERE plan = 'FREE'
        """
    )

    op.execute(
        """
        UPDATE plan_limits
        SET max_records_per_file = 2000000,
            num_presets = 5
        WHERE plan = 'STARTER'
        """
    )
