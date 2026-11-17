import { Canvas, useFrame } from '@react-three/fiber'
import { useMemo, useRef } from 'react'
import * as THREE from 'three'

const NODES = 70
const LINK_DIST = 2.1

/** Deterministic layout so the scene is identical on every launch. */
function buildNetwork(): { points: Float32Array; lines: Float32Array } {
  let seed = 7
  const rnd = () => {
    seed = (seed * 16807) % 2147483647
    return (seed - 1) / 2147483646
  }
  const p = Array.from({ length: NODES }, () => new THREE.Vector3((rnd() - 0.5) * 9, (rnd() - 0.5) * 5, (rnd() - 0.5) * 4))
  const l: number[] = []
  for (let i = 0; i < NODES; i++)
    for (let j = i + 1; j < NODES; j++)
      if (p[i]!.distanceTo(p[j]!) < LINK_DIST) l.push(p[i]!.x, p[i]!.y, p[i]!.z, p[j]!.x, p[j]!.y, p[j]!.z)
  return { points: new Float32Array(p.flatMap((v) => [v.x, v.y, v.z])), lines: new Float32Array(l) }
}

function Network() {
  const group = useRef<THREE.Group>(null)
  const { points, lines } = useMemo(() => buildNetwork(), [])

  useFrame((_, dt) => {
    if (group.current) group.current.rotation.y += dt * 0.05
  })

  return (
    <group ref={group}>
      <lineSegments>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[lines, 3]} />
        </bufferGeometry>
        <lineBasicMaterial color="#8b5cf6" transparent opacity={0.14} />
      </lineSegments>
      <points>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[points, 3]} />
        </bufferGeometry>
        <pointsMaterial color="#22d3ee" size={0.045} sizeAttenuation transparent opacity={0.7} />
      </points>
    </group>
  )
}

export default function NeuralScene() {
  return (
    <Canvas
      camera={{ position: [0, 0, 6.5], fov: 55 }}
      dpr={[1, 1.5]}
      gl={{ antialias: false, powerPreference: 'low-power' }}
      aria-hidden
    >
      <Network />
    </Canvas>
  )
}
