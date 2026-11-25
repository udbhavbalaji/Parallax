export function check(value: number): number {
  return helper(value);
}

function helper(value: number): number {
  return value + 1;
}

export const wrap = (value: number): number => check(value);

export function recurse(value: number): number {
  return value ? recurse(value - 1) : 0;
}
