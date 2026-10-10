-- Seed initial DGCA route weights and sample base period data

insert into route_weight (origin, destination, weight, effective_period)
values
    ('DEL', 'BOM', 0.28500, '2026-01-01'),
    ('DEL', 'BLR', 0.21200, '2026-01-01'),
    ('BOM', 'BLR', 0.18400, '2026-01-01'),
    ('DEL', 'CCU', 0.12600, '2026-01-01'),
    ('BLR', 'HYD', 0.10800, '2026-01-01'),
    ('MAA', 'DEL', 0.08500, '2026-01-01')
on conflict (origin, destination, effective_period) do nothing;
