import { Routes, Route } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { DashboardPage } from "@/pages/DashboardPage";
import { TimelinePage } from "@/pages/TimelinePage";
import { TripDetailPage } from "@/pages/TripDetailPage";
import { EventsPage } from "@/pages/EventsPage";
import { StatisticsPage } from "@/pages/StatisticsPage";
import { MapPage } from "@/pages/MapPage";
import { VideosPage } from "@/pages/VideosPage";
import { LockChimesPage } from "@/pages/LockChimesPage";
import { LightShowsPage } from "@/pages/LightShowsPage";
import { MusicPage } from "@/pages/MusicPage";
import { WrapsPage } from "@/pages/WrapsPage";
import { PlatesPage } from "@/pages/PlatesPage";
import { BoomboxPage } from "@/pages/BoomboxPage";
import { StoragePage } from "@/pages/StoragePage";
import { UsbSettingsPage } from "@/pages/UsbSettingsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { UpdatePage } from "@/pages/UpdatePage";

export default function App() {
  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/timeline" element={<TimelinePage />} />
        <Route path="/trips/:id" element={<TripDetailPage />} />
        <Route path="/events" element={<EventsPage />} />
        <Route path="/statistics" element={<StatisticsPage />} />
        <Route path="/map" element={<MapPage />} />
        <Route path="/videos" element={<VideosPage />} />
        <Route path="/media/chimes" element={<LockChimesPage />} />
        <Route path="/media/lightshows" element={<LightShowsPage />} />
        <Route path="/media/music" element={<MusicPage />} />
        <Route path="/media/wraps" element={<WrapsPage />} />
        <Route path="/media/plates" element={<PlatesPage />} />
        <Route path="/media/boombox" element={<BoomboxPage />} />
        <Route path="/storage" element={<StoragePage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/settings/usb" element={<UsbSettingsPage />} />
        <Route path="/settings/updates" element={<UpdatePage />} />
      </Routes>
    </AppLayout>
  );
}
