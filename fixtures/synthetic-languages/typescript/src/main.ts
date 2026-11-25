import { check, wrap } from "./util";

export function run(value: number): number {
  return check(value) + wrap(value);
}

export class Worker {
  finish(value: number): number { return check(value); }
  run(value: number): number { return this.finish(value); }
}

export function unknown(value: number): number {
  return missing(value);
}

export function shadow(check: (value: number) => number): number {
  return check(1);
}
