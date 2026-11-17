import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { Backend } from '@/lib/useBackend'
import type { CalibrationTimings } from './calibration'
import type { VisionSession } from '../vision/useVisionSession'
import { NeuralCalibration } from './NeuralCalibration'
import { VisionCalibration } from './VisionCalibration'

interface Props {
  mode: 'VISION' | 'NEURAL'
  onModeChange: (m: 'VISION' | 'NEURAL') => void
  backend: Pick<Backend, 'subscribe'>
  session: VisionSession
  onGoLive: () => void
  timings?: Partial<CalibrationTimings>
}

export function CalibrationStudio({ mode, onModeChange, backend, session, onGoLive, timings }: Props) {
  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <h1 className="text-3xl font-semibold tracking-tight">Calibration Studio</h1>
      <p className="mb-6 mt-1 text-sm text-text2">
        Vision calibration uses your real webcam. The Neural tab still shows scripted placeholders (badged DEMO_DATA).
      </p>
      <Tabs value={mode} onValueChange={(v) => onModeChange(v as 'VISION' | 'NEURAL')}>
        <TabsList>
          <TabsTrigger value="VISION">Vision</TabsTrigger>
          <TabsTrigger value="NEURAL">Neural</TabsTrigger>
        </TabsList>
        <TabsContent value="VISION" className="mt-4">
          <VisionCalibration backend={backend} session={session} onGoLive={onGoLive} timings={timings} />
        </TabsContent>
        <TabsContent value="NEURAL" className="mt-4">
          <NeuralCalibration />
        </TabsContent>
      </Tabs>
    </div>
  )
}
