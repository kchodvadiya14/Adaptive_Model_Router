import type { HTMLAttributes, TableHTMLAttributes } from 'react';

export function TableContainer({ children, className = '', ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={`overflow-x-auto rounded-card border border-line ${className}`} {...rest}>
      {children}
    </div>
  );
}

export function Table({ children, className = '', ...rest }: TableHTMLAttributes<HTMLTableElement>) {
  return (
    <table className={`w-full min-w-[640px] text-left text-sm ${className}`} {...rest}>
      {children}
    </table>
  );
}

export function THead({ children, className = '', ...rest }: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <thead className={`bg-surface-3/60 text-ink-secondary ${className}`} {...rest}>
      {children}
    </thead>
  );
}

export function TBody({ children, ...rest }: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody {...rest}>{children}</tbody>;
}

export function Tr({ children, className = '', ...rest }: HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr className={`border-t border-line hover:bg-surface-3/40 ${className}`} {...rest}>
      {children}
    </tr>
  );
}

export function Th({ children, className = '', ...rest }: HTMLAttributes<HTMLTableCellElement>) {
  return (
    <th className={`px-4 py-3 font-medium ${className}`} {...rest}>
      {children}
    </th>
  );
}

export function Td({ children, className = '', ...rest }: HTMLAttributes<HTMLTableCellElement>) {
  return (
    <td className={`px-4 py-3 ${className}`} {...rest}>
      {children}
    </td>
  );
}
