-- some useful SQL commands (for PostgreSQL)

-- show build log
select id, ts, pkgbase, nv_version, pkg_version, elapsed, result, cputime, case when elapsed = 0 then 0 else cputime * 100 / elapsed end as "cpu%", round(memory / 1073741824.0, 3) as "memory (GiB)", substring(msg for 20) as msg, build_reasons #>> '{}' as build_reasons from pkglog order by id desc;

-- show current build status and expected time
select index, c.pkgbase, updated_at, status, elapsed as last_time, c.build_reasons #>> '{}' as build_reasons from pkgcurrent as c left join lateral (
  select elapsed from pkglog where pkgbase = c.pkgbase order by ts desc limit 1
) as log on true order by c.index asc;

-- authorize a group of people to select
create role pkg;
grant connect on database lilac_db to pkg;
grant usage on schema lilac to pkg;
grant select on all tables in schema lilac to pkg;

-- create and grant each user
create role newuser login;
grant pkg to newuser;
