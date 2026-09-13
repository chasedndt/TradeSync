-- UP
-- Market Command drives Hermes jobs through the gateway's own jobs API on its
-- port (PATCH /api/jobs/{id}, pause, resume, run) rather than rewriting the
-- registry file from outside. Directives now record the channel that applied
-- them ('api' for the gateway, 'bridge' for the host bridge's file edit, which
-- stays for the working directory and as the fallback when the gateway is
-- unreachable), and cover the delivery target, pause, resume and run now.

alter table fleet_directives drop constraint if exists fleet_directives_kind_check;
alter table fleet_directives add constraint fleet_directives_kind_check
  check (kind in ('set_schedule', 'set_enabled', 'set_workdir', 'set_deliver', 'pause', 'resume', 'run_now'));

alter table fleet_directives add column if not exists channel text not null default 'bridge';
alter table fleet_directives drop constraint if exists fleet_directives_channel_check;
alter table fleet_directives add constraint fleet_directives_channel_check check (channel in ('bridge', 'api'));

-- DOWN
alter table fleet_directives drop constraint if exists fleet_directives_channel_check;
alter table fleet_directives drop column if exists channel;
alter table fleet_directives drop constraint if exists fleet_directives_kind_check;
alter table fleet_directives add constraint fleet_directives_kind_check
  check (kind in ('set_schedule', 'set_enabled', 'set_workdir'));
