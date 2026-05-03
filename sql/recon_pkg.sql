-- Reconciliation package (Oracle PL/SQL)
--
-- Expected INTERNAL source columns (table or view named by p_internal_source):
--   int_txn_id   NUMBER
--   txn_date     DATE
--   amount       NUMBER
--   currency     VARCHAR2 (optional)
--   reference    VARCHAR2
--   account      VARCHAR2
--
-- Filtering:
--   The package filters internal rows by txn_date = recon_run.run_date.

CREATE OR REPLACE PACKAGE recon_pkg AS
  PROCEDURE run_reconciliation(p_run_id IN NUMBER, p_internal_source IN VARCHAR2);
END recon_pkg;
/

CREATE OR REPLACE PACKAGE BODY recon_pkg AS

  PROCEDURE run_reconciliation(p_run_id IN NUMBER, p_internal_source IN VARCHAR2) AS
    v_run_date DATE;
    v_rule_id  NUMBER;

    v_ext_cnt NUMBER := 0;
    v_ext_amt NUMBER := 0;
    v_int_cnt NUMBER := 0;
    v_int_amt NUMBER := 0;
    v_mch_cnt NUMBER := 0;
    v_mch_amt NUMBER := 0;
    v_brk_cnt NUMBER := 0;
    v_brk_amt NUMBER := 0;
  BEGIN
    SELECT run_date INTO v_run_date
    FROM recon_run
    WHERE run_id = p_run_id
    FOR UPDATE;

    -- Allow rerun for same run_id
    DELETE FROM recon_match WHERE run_id = p_run_id;
    DELETE FROM recon_break WHERE run_id = p_run_id;
    DELETE FROM recon_metrics WHERE run_id = p_run_id;

    SELECT rule_id INTO v_rule_id
    FROM recon_rule
    WHERE rule_name = 'EXACT_REF_AMT_DATE_ACCT'
      AND active_flag = 'Y'
    FETCH FIRST 1 ROWS ONLY;

    -- External totals
    SELECT COUNT(*), NVL(SUM(amount), 0)
      INTO v_ext_cnt, v_ext_amt
    FROM txn_canonical_ext
    WHERE run_id = p_run_id;

    -- Internal totals (dynamic)
    EXECUTE IMMEDIATE
      'SELECT COUNT(*), NVL(SUM(amount),0) FROM ' || p_internal_source || ' WHERE txn_date = :d'
      INTO v_int_cnt, v_int_amt
      USING v_run_date;

    -- 1) Exact 4-key match (reference + amount + txn_date + account), enforcing 1-to-1
    EXECUTE IMMEDIATE
      'INSERT INTO recon_match (run_id, rule_id, ext_txn_id, int_txn_id, match_type, match_score) ' ||
      'SELECT :run_id, :rule_id, ext_txn_id, int_txn_id, ''EXACT_4KEY'', 1.00 ' ||
      'FROM ( ' ||
      '  SELECT ' ||
      '    e.ext_txn_id, i.int_txn_id, ' ||
      '    ROW_NUMBER() OVER (PARTITION BY e.ext_txn_id ORDER BY i.int_txn_id) rn_e, ' ||
      '    ROW_NUMBER() OVER (PARTITION BY i.int_txn_id ORDER BY e.ext_txn_id) rn_i ' ||
      '  FROM txn_canonical_ext e ' ||
      '  JOIN ' || p_internal_source || ' i ' ||
      '    ON NVL(UPPER(TRIM(e.reference)), ''~'') = NVL(UPPER(TRIM(i.reference)), ''~'') ' ||
      '   AND e.amount = i.amount ' ||
      '   AND e.txn_date = i.txn_date ' ||
      '   AND NVL(UPPER(TRIM(e.account)), ''~'') = NVL(UPPER(TRIM(i.account)), ''~'') ' ||
      '  WHERE e.run_id = :run_id ' ||
      '    AND i.txn_date = :run_date ' ||
      ') x ' ||
      'WHERE x.rn_e = 1 AND x.rn_i = 1'
      USING p_run_id, v_rule_id, p_run_id, v_run_date;

    -- Matched totals (from external side)
    SELECT COUNT(*), NVL(SUM(e.amount), 0)
      INTO v_mch_cnt, v_mch_amt
    FROM recon_match m
    JOIN txn_canonical_ext e ON e.ext_txn_id = m.ext_txn_id
    WHERE m.run_id = p_run_id;

    -- External-only breaks
    INSERT INTO recon_break (run_id, break_code, break_reason, ext_txn_id, amount, txn_date, reference, account)
    SELECT
      p_run_id,
      'EXT_ONLY',
      'External txn not matched to internal',
      e.ext_txn_id,
      e.amount,
      e.txn_date,
      e.reference,
      e.account
    FROM txn_canonical_ext e
    LEFT JOIN recon_match m
      ON m.run_id = p_run_id AND m.ext_txn_id = e.ext_txn_id
    WHERE e.run_id = p_run_id
      AND m.match_id IS NULL;

    -- Internal-only breaks
    EXECUTE IMMEDIATE
      'INSERT INTO recon_break (run_id, break_code, break_reason, int_txn_id, amount, txn_date, reference, account) ' ||
      'SELECT ' ||
      '  :run_id, ''INT_ONLY'', ''Internal txn not matched to external'', i.int_txn_id, i.amount, i.txn_date, i.reference, i.account ' ||
      'FROM ' || p_internal_source || ' i ' ||
      'LEFT JOIN recon_match m ' ||
      '  ON m.run_id = :run_id AND m.int_txn_id = i.int_txn_id ' ||
      'WHERE i.txn_date = :run_date ' ||
      '  AND m.match_id IS NULL'
      USING p_run_id, p_run_id, v_run_date;

    SELECT COUNT(*), NVL(SUM(amount), 0)
      INTO v_brk_cnt, v_brk_amt
    FROM recon_break
    WHERE run_id = p_run_id;

    INSERT INTO recon_metrics (
      run_id,
      ext_total_count, ext_total_amount,
      int_total_count, int_total_amount,
      matched_count, matched_amount,
      break_count, break_amount
    ) VALUES (
      p_run_id,
      v_ext_cnt, v_ext_amt,
      v_int_cnt, v_int_amt,
      v_mch_cnt, v_mch_amt,
      v_brk_cnt, v_brk_amt
    );

    UPDATE recon_run
      SET status = 'RECONCILED'
    WHERE run_id = p_run_id;
  END run_reconciliation;

END recon_pkg;
/
