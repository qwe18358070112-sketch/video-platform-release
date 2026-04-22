from __future__ import annotations

"""宫格映射与轮询顺序重排。

这一版把“物理槽位”和“轮询顺序”拆开处理：
- 先生成物理槽位（规则网格或模板网格）
- 再按顺序策略重排输出列表
这样可以同时支持：
1. 从左到右 / 从上到下
2. 自定义顺序
3. 根据收藏夹名称排序
4. 不同形态的 12 宫格模板
"""

from common import GridCell, GridConfig, Rect


class GridMapper:
    def __init__(self, grid_config: GridConfig):
        self._config = grid_config

    def build_cells(
        self,
        preview_rect: Rect,
        layout: int | None = None,
        runtime_label_order: list[str] | None = None,
        order_override: str | None = None,
    ) -> list[GridCell]:
        physical_cells = self._build_physical_cells(preview_rect, layout)
        if not physical_cells:
            return []

        order = order_override or self._config.order
        if order == "row_major":
            return sorted(physical_cells, key=lambda cell: (cell.row, cell.col, cell.index))
        if order == "column_major":
            return sorted(physical_cells, key=lambda cell: (cell.col, cell.row, cell.index))
        if order == "custom":
            return self._reorder_by_indexes(physical_cells, self._config.resolved_custom_sequence(len(physical_cells)))
        if order == "favorites_name":
            sequence = self._config.resolved_favorites_sequence(runtime_label_order or [], len(physical_cells))
            return self._reorder_by_indexes(physical_cells, sequence)
        return sorted(physical_cells, key=lambda cell: (cell.row, cell.col, cell.index))

    def _build_physical_cells(self, preview_rect: Rect, layout: int | None = None) -> list[GridCell]:
        template_slots = self._config.selected_template()
        target_layout = self._config.layout if layout is None else int(layout)
        if template_slots and target_layout == self._config.layout:
            # 关键修复：模板宫格只对“配置里声明的那个布局”生效。
            # 如果运行时已经同步到了 4/6/9 等其他宫格，不能继续沿用 12 宫格模板，
            # 否则主流程会把真实宫格误切成错误数量的槽位。
            return [self._cell_from_template_slot(preview_rect, slot_index, slot) for slot_index, slot in enumerate(template_slots)]
        return self._build_regular_cells(preview_rect, target_layout)

    def _build_regular_cells(self, preview_rect: Rect, layout: int | None = None) -> list[GridCell]:
        spec = self._config.grid_spec_for_layout(layout)
        cell_width = preview_rect.width / spec.cols
        cell_height = preview_rect.height / spec.rows
        padding_x = int(cell_width * self._config.cell_padding_ratio)
        padding_y = int(cell_height * self._config.cell_padding_ratio)

        cells: list[GridCell] = []
        physical_index = 0
        for row in range(spec.rows):
            for col in range(spec.cols):
                cell_rect = Rect(
                    left=int(preview_rect.left + col * cell_width),
                    top=int(preview_rect.top + row * cell_height),
                    right=int(preview_rect.left + (col + 1) * cell_width),
                    bottom=int(preview_rect.top + (row + 1) * cell_height),
                )
                cells.append(
                    self._create_cell(
                        physical_index=physical_index,
                        row=row,
                        col=col,
                        cell_rect=cell_rect,
                        padding_x=padding_x,
                        padding_y=padding_y,
                        label=self._config.cell_labels.get(physical_index, ""),
                    )
                )
                physical_index += 1
        return cells

    def _cell_from_template_slot(self, preview_rect: Rect, physical_index: int, slot) -> GridCell:
        cell_rect = slot.to_rect(preview_rect)
        padding_x = int(cell_rect.width * self._config.cell_padding_ratio)
        padding_y = int(cell_rect.height * self._config.cell_padding_ratio)
        label = slot.label or self._config.cell_labels.get(physical_index, "")
        return self._create_cell(
            physical_index=physical_index,
            row=slot.row,
            col=slot.col,
            cell_rect=cell_rect,
            padding_x=padding_x,
            padding_y=padding_y,
            label=label,
        )

    def _create_cell(
        self,
        *,
        physical_index: int,
        row: int,
        col: int,
        cell_rect: Rect,
        padding_x: int,
        padding_y: int,
        label: str,
    ) -> GridCell:
        inner_rect = cell_rect.inset(padding_x, padding_y)
        row_key = row + 1
        click_ratio_y = self._config.click_point_ratio_y_by_row.get(row_key, self._config.click_point_ratio_y)
        zoom_ratio_y = self._config.zoom_point_ratio_y_by_row.get(row_key, self._config.zoom_point_ratio_y)
        select_x = cell_rect.left + int(cell_rect.width * self._config.click_point_ratio_x)
        select_y = cell_rect.top + int(cell_rect.height * click_ratio_y)
        select_x = max(cell_rect.left + 2, min(cell_rect.right - 2, select_x))
        select_y = max(cell_rect.top + 2, min(cell_rect.bottom - 2, select_y))
        zoom_x = cell_rect.left + int(cell_rect.width * self._config.zoom_point_ratio_x)
        zoom_y = cell_rect.top + int(cell_rect.height * zoom_ratio_y)
        zoom_x = max(cell_rect.left + 2, min(cell_rect.right - 2, zoom_x))
        zoom_y = max(cell_rect.top + 2, min(cell_rect.bottom - 2, zoom_y))
        return GridCell(
            index=physical_index,
            row=row,
            col=col,
            rect=inner_rect,
            cell_rect=cell_rect,
            select_point=(select_x, select_y),
            # 放大点击不再落在单元格中部，而是收敛到“中间偏上”。
            # 现场反馈表明正中心更容易撞到弱响应区或遮挡层，尤其是全屏宫格里的中下部区域。
            zoom_point=(zoom_x, zoom_y),
            label=label,
        )

    def _reorder_by_indexes(self, cells: list[GridCell], sequence: tuple[int, ...]) -> list[GridCell]:
        by_index = {cell.index: cell for cell in cells}
        ordered: list[GridCell] = []
        seen: set[int] = set()
        for index in sequence:
            cell = by_index.get(index)
            if cell is None or index in seen:
                continue
            ordered.append(cell)
            seen.add(index)
        if len(ordered) == len(cells):
            return ordered
        for cell in sorted(cells, key=lambda item: (item.row, item.col, item.index)):
            if cell.index not in seen:
                ordered.append(cell)
        return ordered
