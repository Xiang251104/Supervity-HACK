-- AP Control Tower — Round 2 Supabase schema
-- Generated from the organizer pack. Dirty columns are TEXT on purpose:
-- the Operators normalize comma-decimals and mixed date formats at runtime.
-- Run this whole file in the Supabase SQL editor, then import the CSVs in ./import/.

drop table if exists public.ap_invoices cascade;
create table public.ap_invoices (
  id bigserial primary key,
  belnr text,
  gjahr text,
  xblnr text,
  lifnr text,
  ebeln text,
  bldat text,
  budat text,
  waers text,
  wrbtr text,
  mwskz text,
  source_channel text,
  bank_on_inv text,
  gl_code text,
  status text,
  usnam text,
  submit_ts text,
  confidence numeric,
  gst_amt numeric,
  bukrs_on_inv text,
  po_waers text
);
create index on public.ap_invoices (belnr);
create index on public.ap_invoices (lifnr);
create index on public.ap_invoices (ebeln);
create index on public.ap_invoices (xblnr);

drop table if exists public.vendor_master cascade;
create table public.vendor_master (
  id bigserial primary key,
  lifnr text,
  name1 text,
  stcd1 text,
  banks text,
  bankl text,
  bankn text,
  waers text,
  zterm text,
  ktokk text,
  sperr text,
  loevm text,
  land1 text,
  last_bank_chg text,
  email text,
  erdat text
);
create index on public.vendor_master (lifnr);

drop table if exists public.po_headers cascade;
create table public.po_headers (
  id bigserial primary key,
  ebeln text,
  bukrs text,
  bsart text,
  lifnr text,
  ekorg text,
  ekgrp text,
  waers text,
  zterm text,
  aedat text,
  ernam text,
  procstat text,
  wkurs numeric,
  kdatb text,
  kdate text,
  netwr numeric
);
create index on public.po_headers (ebeln);
create index on public.po_headers (lifnr);
create index on public.po_headers (bukrs);

drop table if exists public.po_items cascade;
create table public.po_items (
  id bigserial primary key,
  ebeln text,
  ebelp text,
  txz01 text,
  matnr text,
  werks text,
  matkl text,
  menge numeric,
  meins text,
  netpr numeric,
  peinh numeric,
  netwr numeric,
  mwskz text,
  uebto numeric,
  untto numeric,
  elikz text,
  knttp text
);
create index on public.po_items (ebeln);
create index on public.po_items (ebelp);
create index on public.po_items (matnr);

drop table if exists public.goods_receipts cascade;
create table public.goods_receipts (
  id bigserial primary key,
  mblnr text,
  zeile text,
  ebeln text,
  ebelp text,
  bwart text,
  budat text,
  menge numeric,
  meins text,
  matnr text,
  werks text,
  shkzg text
);
create index on public.goods_receipts (ebeln);
create index on public.goods_receipts (ebelp);

drop table if exists public.gl_master cascade;
create table public.gl_master (
  id bigserial primary key,
  saknr text,
  txt50 text,
  ktoks text,
  kostl_allowed text
);
create index on public.gl_master (saknr);

drop table if exists public.doa_matrix cascade;
create table public.doa_matrix (
  id bigserial primary key,
  role text,
  approver text,
  email text,
  min_amt numeric,
  max_amt numeric,
  kostl text
);
create index on public.doa_matrix (kostl);

drop table if exists public.pricing_conditions cascade;
create table public.pricing_conditions (
  id bigserial primary key,
  knumh text,
  kopos text,
  kappl text,
  kschl text,
  krech text,
  kbetr numeric,
  konwa text,
  kpein numeric,
  kmein text,
  datab text,
  datbi text
);
create index on public.pricing_conditions (knumh);
create index on public.pricing_conditions (kschl);

drop table if exists public.company_codes cascade;
create table public.company_codes (
  id bigserial primary key,
  bukrs text,
  butxt text,
  land1 text,
  waers text,
  ktopl text,
  erdat text
);
create index on public.company_codes (bukrs);

drop table if exists public.fx_rates cascade;
create table public.fx_rates (
  id bigserial primary key,
  gdatu text,
  fcurr text,
  tcurr text,
  ukurs numeric,
  ffact numeric,
  tfact numeric
);
create index on public.fx_rates (fcurr);
create index on public.fx_rates (tcurr);
create index on public.fx_rates (gdatu);

drop table if exists public.bank_master cascade;
create table public.bank_master (
  id bigserial primary key,
  lifnr text,
  bank_seq text,
  banks text,
  bankl text,
  bankn text,
  valid_from text,
  valid_to text,
  is_current text,
  change_source text,
  changed_by text
);
create index on public.bank_master (lifnr);
create index on public.bank_master (bankn);
create index on public.bank_master (is_current);

drop table if exists public.email_headers cascade;
create table public.email_headers (
  id bigserial primary key,
  email_id text,
  belnr text,
  lifnr text,
  from_addr text,
  to_addr text,
  subject text,
  recv_ts text,
  spf text,
  dkim text,
  dmarc text,
  msg_type text,
  attach_name text
);
create index on public.email_headers (lifnr);
create index on public.email_headers (belnr);
create index on public.email_headers (msg_type);

drop table if exists public.discount_schedule cascade;
create table public.discount_schedule (
  id bigserial primary key,
  lifnr text,
  zterm text,
  disc_pct numeric,
  disc_days numeric,
  net_days numeric,
  valid_from text,
  valid_to text
);
create index on public.discount_schedule (lifnr);

drop table if exists public.approval_log cascade;
create table public.approval_log (
  id bigserial primary key,
  log_id text,
  belnr text,
  wrbtr numeric,
  role text,
  approver text,
  email text,
  action text,
  decision_ts text,
  policy_ref text,
  comment text
);
create index on public.approval_log (belnr);
create index on public.approval_log (policy_ref);

-- belnr verified unique across the pack
create unique index on public.ap_invoices (belnr);

-- Row counts to verify after import:
--   ap_invoices          450
--   vendor_master        80
--   po_headers           153
--   po_items             276
--   goods_receipts       135
--   gl_master            14
--   doa_matrix           10
--   pricing_conditions   135
--   company_codes        6
--   fx_rates             894
--   bank_master          114
--   email_headers        78
--   discount_schedule    79
--   approval_log         141

select 'ap_invoices' t, count(*) from public.ap_invoices
union all select 'vendor_master', count(*) from public.vendor_master
union all select 'po_headers', count(*) from public.po_headers
union all select 'po_items', count(*) from public.po_items
union all select 'goods_receipts', count(*) from public.goods_receipts
union all select 'gl_master', count(*) from public.gl_master
union all select 'doa_matrix', count(*) from public.doa_matrix
union all select 'pricing_conditions', count(*) from public.pricing_conditions
union all select 'company_codes', count(*) from public.company_codes
union all select 'fx_rates', count(*) from public.fx_rates
union all select 'bank_master', count(*) from public.bank_master
union all select 'email_headers', count(*) from public.email_headers
union all select 'discount_schedule', count(*) from public.discount_schedule
union all select 'approval_log', count(*) from public.approval_log
order by 1;
