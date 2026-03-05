'use client';

import * as React from 'react';
import * as Popover from '@radix-ui/react-popover';
import { Check, ChevronDown, Search, X } from 'lucide-react';
import { cn } from '@/utils/cn';
import {
  HASH_TYPES,
  HASH_TYPE_CATEGORIES,
  type HashType,
} from '@/data/hashTypes';

interface HashTypeComboboxProps {
  value: string; // mode number string, e.g. "0"
  onChange: (mode: string) => void;
  className?: string;
  disabled?: boolean;
}

export function HashTypeCombobox({
  value,
  onChange,
  className,
  disabled = false,
}: HashTypeComboboxProps) {
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState('');
  const searchRef = React.useRef<HTMLInputElement>(null);
  const listRef = React.useRef<HTMLDivElement>(null);

  const selected = React.useMemo(
    () => HASH_TYPES.find((h) => h.mode === value) ?? null,
    [value]
  );

  // Filter by name OR mode number
  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return HASH_TYPES;
    return HASH_TYPES.filter(
      (h) =>
        h.name.toLowerCase().includes(q) ||
        h.mode.includes(q)
    );
  }, [query]);

  // Group filtered results by category (preserving category order)
  const grouped = React.useMemo(() => {
    const map = new Map<string, HashType[]>();
    for (const cat of HASH_TYPE_CATEGORIES) {
      const items = filtered.filter((h) => h.category === cat);
      if (items.length > 0) map.set(cat, items);
    }
    return map;
  }, [filtered]);

  const totalFiltered = filtered.length;

  // Focus search input when popover opens
  React.useEffect(() => {
    if (open) {
      // small delay to let popover render
      const t = setTimeout(() => searchRef.current?.focus(), 50);
      return () => clearTimeout(t);
    } else {
      setQuery('');
    }
  }, [open]);

  const handleSelect = (mode: string) => {
    onChange(mode);
    setOpen(false);
  };

  const handleClearSearch = () => {
    setQuery('');
    searchRef.current?.focus();
  };

  return (
    <Popover.Root open={open} onOpenChange={disabled ? undefined : setOpen}>
      <Popover.Trigger asChild>
        <button
          type="button"
          disabled={disabled}
          aria-expanded={open}
          aria-haspopup="listbox"
          className={cn(
            'flex h-10 w-full items-center justify-between rounded-lg border',
            'border-slate-600/50 bg-slate-800/50 px-3 py-2 text-sm',
            'text-slate-200 transition-colors',
            'hover:border-slate-500/70 hover:bg-slate-800/70',
            'focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20',
            'disabled:cursor-not-allowed disabled:opacity-50',
            open && 'border-blue-500/50 ring-1 ring-blue-500/20',
            className
          )}
        >
          <span className="truncate">
            {selected ? (
              <>
                <span className="text-slate-400 font-mono text-xs mr-2">
                  {selected.mode}
                </span>
                {selected.name}
              </>
            ) : (
              <span className="text-slate-500">Select hash type…</span>
            )}
          </span>
          <ChevronDown
            className={cn(
              'ml-2 h-4 w-4 shrink-0 text-slate-400 transition-transform duration-150',
              open && 'rotate-180'
            )}
          />
        </button>
      </Popover.Trigger>

      <Popover.Portal>
        <Popover.Content
          sideOffset={4}
          align="start"
          className={cn(
            'z-50 w-[var(--radix-popover-trigger-width)] overflow-hidden rounded-lg',
            'border border-slate-600/50 bg-slate-900 shadow-xl shadow-black/40',
            'data-[state=open]:animate-in data-[state=closed]:animate-out',
            'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
            'data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95',
            'data-[side=bottom]:slide-in-from-top-2 data-[side=top]:slide-in-from-bottom-2'
          )}
          style={{ maxHeight: '22rem' }}
        >
          {/* Search input */}
          <div className="flex items-center border-b border-slate-700/60 px-3 py-2 gap-2">
            <Search className="h-4 w-4 shrink-0 text-slate-500" />
            <input
              ref={searchRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by name or mode number…"
              className={cn(
                'flex-1 bg-transparent text-sm text-slate-200',
                'placeholder:text-slate-500',
                'focus:outline-none'
              )}
              onKeyDown={(e) => {
                if (e.key === 'Escape') {
                  if (query) {
                    e.stopPropagation();
                    setQuery('');
                  }
                }
              }}
            />
            {query && (
              <button
                type="button"
                onClick={handleClearSearch}
                className="text-slate-500 hover:text-slate-300 transition-colors"
                tabIndex={-1}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          {/* Results */}
          <div
            ref={listRef}
            role="listbox"
            aria-label="Hash types"
            className="overflow-y-auto"
            style={{ maxHeight: '18rem' }}
          >
            {totalFiltered === 0 ? (
              <div className="px-3 py-6 text-center text-sm text-slate-500">
                No results for &ldquo;{query}&rdquo;
              </div>
            ) : (
              Array.from(grouped.entries()).map(([category, items]) => (
                <div key={category}>
                  {/* Category header */}
                  <div className="sticky top-0 z-10 bg-slate-900/95 backdrop-blur-sm px-3 py-1.5 border-b border-slate-700/40">
                    <span className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
                      {category}
                    </span>
                    <span className="ml-2 text-[10px] text-slate-600">
                      {items.length}
                    </span>
                  </div>
                  {/* Items */}
                  {items.map((hashType) => {
                    const isSelected = hashType.mode === value;
                    return (
                      <button
                        key={hashType.mode}
                        type="button"
                        role="option"
                        aria-selected={isSelected}
                        onClick={() => handleSelect(hashType.mode)}
                        className={cn(
                          'flex w-full items-center gap-2 px-3 py-2 text-sm transition-colors',
                          'hover:bg-slate-800/70 focus:outline-none focus:bg-slate-800/70',
                          isSelected && 'bg-blue-600/15 text-blue-300'
                        )}
                      >
                        <span className="w-4 shrink-0">
                          {isSelected && (
                            <Check className="h-3.5 w-3.5 text-blue-400" />
                          )}
                        </span>
                        <span
                          className={cn(
                            'font-mono text-xs w-12 shrink-0 text-right',
                            isSelected ? 'text-blue-400/80' : 'text-slate-500'
                          )}
                        >
                          {hashType.mode}
                        </span>
                        <span
                          className={cn(
                            'truncate',
                            isSelected ? 'text-blue-200' : 'text-slate-300'
                          )}
                        >
                          {hashType.name}
                        </span>
                      </button>
                    );
                  })}
                </div>
              ))
            )}
          </div>

          {/* Footer: result count */}
          {query && totalFiltered > 0 && (
            <div className="border-t border-slate-700/40 px-3 py-1.5 text-xs text-slate-600">
              {totalFiltered} result{totalFiltered !== 1 ? 's' : ''}
            </div>
          )}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
