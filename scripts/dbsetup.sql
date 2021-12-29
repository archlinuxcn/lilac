create schema if not exists lilac;
set search_path to lilac;

create type buildresult as enum ('successful', 'failed', 'skipped', 'staged');

create table pkglog (
  id serial primary key,
  ts timestamp with time zone not null default current_timestamp,
  pkgbase text not null,
  nv_version text,
  pkg_version text,
  elapsed int not null,
  result buildresult not null,
  cputime int,
  maxrss bigint,
  msg text
);

create index pkglog_ts_idx on pkglog (ts);
create index pkglog_pkgbase_idx on pkglog (pkgbase);

create type batchevent as enum ('start', 'stop');

create table batch (
  id serial primary key,
  ts timestamp with time zone not null default current_timestamp,
  event batchevent not null
);

create index batch_ts_idx on batch (ts);
