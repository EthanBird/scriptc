export type ConfigValue = string | string[] | undefined;
export type Config = Record<string, ConfigValue>;
export declare function getConfig(): Config;
export declare class Box {
  constructor(value: string);
  value(): string;
}
export type BoxAlias = Box;
