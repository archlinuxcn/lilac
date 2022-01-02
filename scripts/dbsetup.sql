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
  memory bigint,
  msg text,
  build_reasons jsonb
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

create type buildstatus as enum ('pending', 'building', 'done');

CREATE OR REPLACE FUNCTION updated_at_trigger()
RETURNS TRIGGER AS $$
BEGIN
   IF row(NEW.*) IS DISTINCT FROM row(OLD.*) THEN
      NEW.updated_at = now();
      RETURN NEW;
   ELSE
      RETURN OLD;
   END IF;
   RETURN NEW;
END;
$$ language 'plpgsql';

create table pkgcurrent (
  id serial primary key,
  ts timestamp with time zone not null default current_timestamp,
  updated_at timestamp with time zone not null default current_timestamp,
  pkgbase text unique not null,
  index integer not null,
  status buildstatus not null,
  build_reasons jsonb not null
);

CREATE TRIGGER pkgcurrent_updated BEFORE UPDATE
  ON pkgcurrent FOR EACH ROW EXECUTE PROCEDURE updated_at_trigger();

