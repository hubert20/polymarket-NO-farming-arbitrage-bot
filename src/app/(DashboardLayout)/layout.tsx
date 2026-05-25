"use client";
import { styled, Container, Box } from "@mui/material";
import React, { useState } from "react";
import Header from "@/app/(DashboardLayout)/layout/header/Header";
import Sidebar from "@/app/(DashboardLayout)/layout/sidebar/Sidebar";
import { BotProvider } from "@/context/BotContext";

const MainWrapper = styled("div")(() => ({
  display: "flex",
  minHeight: "100vh",
  width: "100%",
}));

const PageWrapper = styled("div")(() => ({
  display: "flex",
  flexGrow: 1,
  paddingBottom: "60px",
  flexDirection: "column",
  zIndex: 1,
  backgroundColor: "transparent",
  minWidth: 0,
  width: "100%",
}));

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [isSidebarOpen, setSidebarOpen] = useState(true);
  const [isMobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  return (
    <BotProvider>
      <MainWrapper className="mainwrapper">
        <Sidebar
          isSidebarOpen={isSidebarOpen}
          isMobileSidebarOpen={isMobileSidebarOpen}
          onSidebarClose={() => setMobileSidebarOpen(false)}
        />
        <PageWrapper className="page-wrapper">
          <Header toggleMobileSidebar={() => setMobileSidebarOpen(true)} />
          <Container
            maxWidth="xl"
            sx={{
              paddingTop: "20px",
              width: "100%",
              minWidth: 0,
            }}
          >
            <Box sx={{ minHeight: "calc(100vh - 170px)", width: "100%", minWidth: 0 }}>
              {children}
            </Box>
          </Container>
        </PageWrapper>
      </MainWrapper>
    </BotProvider>
  );
}
