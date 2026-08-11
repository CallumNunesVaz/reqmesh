import { describe, it, expect } from 'vitest';
import { matrixToCsv } from '../src/lib/matrixCsv';

describe('matrixToCsv', () => {
  it('produces a header and rows with x for set cells', () => {
    const result = matrixToCsv({
      rowHeader: 'Requirement',
      columns: [
        { id: 'c1', label: 'Engine' },
        { id: 'c2', label: 'Wing' },
      ],
      rows: [
        { id: 'r1', label: 'REQ-001', cells: [true, false] },
        { id: 'r2', label: 'REQ-002', cells: [false, true] },
      ],
    });
    expect(result).toBe(
      'Requirement,Engine,Wing\r\n' +
      'REQ-001,x,\r\n' +
      'REQ-002,,x\r\n',
    );
  });

  it('handles an empty rows array and still produces the header', () => {
    const result = matrixToCsv({
      rowHeader: 'Source',
      columns: [{ id: 'c1', label: 'Target A' }],
      rows: [],
    });
    expect(result).toBe('Source,Target A\r\n');
  });

  it('quotes a field containing a comma', () => {
    const result = matrixToCsv({
      rowHeader: 'Requirement',
      columns: [{ id: 'c1', label: 'a, b' }],
      rows: [{ id: 'r1', label: 'REQ-001', cells: [true] }],
    });
    expect(result).toBe(
      'Requirement,"a, b"\r\n' +
      'REQ-001,x\r\n',
    );
  });

  it('quotes a field containing a double quote and doubles inner quotes', () => {
    const result = matrixToCsv({
      rowHeader: 'Requirement',
      columns: [{ id: 'c1', label: 'He said "yes"' }],
      rows: [{ id: 'r1', label: 'REQ-001', cells: [true] }],
    });
    expect(result).toBe(
      'Requirement,"He said ""yes"""\r\n' +
      'REQ-001,x\r\n',
    );
  });

  it('quotes a field with a leading space', () => {
    const result = matrixToCsv({
      rowHeader: ' Source',
      columns: [{ id: 'c1', label: 'Col' }],
      rows: [],
    });
    expect(result).toBe('" Source",Col\r\n');
  });

  it('quotes a field with a trailing space', () => {
    const result = matrixToCsv({
      rowHeader: 'Source ',
      columns: [{ id: 'c1', label: 'Col' }],
      rows: [],
    });
    expect(result).toBe('"Source ",Col\r\n');
  });

  it('quotes a field with a newline', () => {
    const result = matrixToCsv({
      rowHeader: 'Requirement',
      columns: [{ id: 'c1', label: 'Line\nBreak' }],
      rows: [],
    });
    expect(result).toBe('Requirement,"Line\nBreak"\r\n');
  });

  it('quotes a field with a carriage return', () => {
    const result = matrixToCsv({
      rowHeader: 'Requirement',
      columns: [{ id: 'c1', label: 'Line\rBreak' }],
      rows: [],
    });
    expect(result).toBe('Requirement,"Line\rBreak"\r\n');
  });

  it('preserves row and column order as given', () => {
    const result = matrixToCsv({
      rowHeader: 'R',
      columns: [
        { id: 'z', label: 'Zulu' },
        { id: 'a', label: 'Alpha' },
      ],
      rows: [
        { id: 'b', label: 'Bravo', cells: [false, true] },
        { id: 'a', label: 'Alpha', cells: [true, false] },
      ],
    });
    expect(result).toBe(
      'R,Zulu,Alpha\r\n' +
      'Bravo,,x\r\n' +
      'Alpha,x,\r\n',
    );
  });

  it('uses CRLF line endings', () => {
    const result = matrixToCsv({
      rowHeader: 'R',
      columns: [{ id: 'c1', label: 'C' }],
      rows: [{ id: 'r1', label: 'Row', cells: [true] }],
    });
    expect(result).toContain('\r\n');
    // The header line and the data line each end with CRLF.
    const lines = result.split('\r\n');
    expect(lines).toHaveLength(3); // 'R,C', 'Row,x', '' (trailing)
  });

  it('handles a name with comma and a name with double quote on the same row', () => {
    const result = matrixToCsv({
      rowHeader: 'Requirement',
      columns: [
        { id: 'c1', label: 'a, b' },
        { id: 'c2', label: 'He said "yes"' },
      ],
      rows: [
        { id: 'r1', label: 'REQ-001', cells: [true, false] },
      ],
    });
    expect(result).toBe(
      'Requirement,"a, b","He said ""yes"""\r\n' +
      'REQ-001,x,\r\n',
    );
  });

  it('handles a row label with a comma', () => {
    const result = matrixToCsv({
      rowHeader: 'R',
      columns: [{ id: 'c1', label: 'Col' }],
      rows: [{ id: 'r1', label: 'Name, with comma', cells: [true] }],
    });
    expect(result).toBe('R,Col\r\n"Name, with comma",x\r\n');
  });

  it('handles a row label with double quotes', () => {
    const result = matrixToCsv({
      rowHeader: 'R',
      columns: [{ id: 'c1', label: 'Col' }],
      rows: [{ id: 'r1', label: 'He said "yes"', cells: [false] }],
    });
    expect(result).toBe('R,Col\r\n"He said ""yes""",\r\n');
  });
});
