import type { CSSProperties } from "react";
import styles from "./cube-field.module.css";

type Cell = [number, number, number];

/** Bloc 3×3×3 plein + six cubes détachés sur les axes : un cube qui se défait. Positions fixes (pas d'aléatoire au rendu). */
const DENSE: Cell[] = [
  ...[-1, 0, 1].flatMap((x) => [-1, 0, 1].flatMap((y) => [-1, 0, 1].map((z) => [x, y, z] as Cell))),
  [2, 0, 0], [-2, 0, 0], [0, 2, 0], [0, -2, 0], [0, 0, 2], [0, 0, -2],
];
const SINGLE: Cell[] = [[0, 0, 0]];

/**
 * Amas de cubes bleus en mouvement (CSS 3D pur).
 * `size` : côté de l'amas en pixels ; `single` : un seul cube ; `imploding` : les cubes rentrent au centre et disparaissent.
 */
export function CubeField({ size = 44, single = false, imploding = false, className, style }: {
  size?: number; single?: boolean; imploding?: boolean; className?: string; style?: CSSProperties;
}) {
  const cells = single ? SINGLE : DENSE;
  const cube = single ? size * 0.55 : size / 5.4;
  const step = cube * 1.12;
  const half = cube / 2;
  const faces = [
    `translateZ(${half}px)`,
    `rotateY(90deg) translateZ(${half}px)`,
    `rotateX(90deg) translateZ(${half}px)`,
    `rotateY(180deg) translateZ(${half}px)`,
    `rotateY(-90deg) translateZ(${half}px)`,
    `rotateX(-90deg) translateZ(${half}px)`,
  ];
  return (
    <div className={`${styles.scene} ${imploding ? styles.imploding : ""} ${className ?? ""}`}
      style={{ width: size, height: size, ...style }} aria-hidden="true">
      <div className={styles.cluster} style={{ width: 0, height: 0 }}>
        {cells.map(([x, y, z], i) => (
          <div
            key={i}
            className={styles.cube}
            style={{
              width: cube, height: cube, marginLeft: -half, marginTop: -half,
              "--x": `${x * step}px`, "--y": `${y * step}px`, "--z": `${z * step}px`,
              animationDelay: imploding ? `${(i % 9) * 0.03}s` : `${-(i * 0.17).toFixed(2)}s`,
            } as CSSProperties}
          >
            {faces.map((t, f) => <div key={f} className={styles.face} style={{ transform: t }} />)}
          </div>
        ))}
      </div>
    </div>
  );
}
