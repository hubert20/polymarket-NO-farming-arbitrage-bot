import React from "react";
import Menuitems from "./MenuItems";
import { Box } from "@mui/material";
import {
  Sidebar as MUI_Sidebar,
  Menu,
  MenuItem,
  Submenu,
} from "react-mui-sidebar";
import { IconPoint } from '@tabler/icons-react';
import Link from "next/link";
import { usePathname } from "next/navigation";

import AppLogo from "@/components/bot/AppLogo";

const renderMenuItems = (items: any, pathDirect: any) => {

  return items.map((item: any) => {

    const Icon = item.icon ? item.icon : IconPoint;

    const itemIcon = <Icon stroke={1.5} size="1.3rem" />;

    if (item.subheader) {
      return (
        <Menu
          subHeading={item.subheader}
          key={item.subheader}
        />
      );
    }

    if (item.children) {
      return (
        <Submenu
          key={item.id}
          title={item.title}
          icon={itemIcon}
          borderRadius='7px'
        >
          {renderMenuItems(item.children, pathDirect)}
        </Submenu>
      );
    }

    return (
      <Box px={3} key={item.id}>
        <MenuItem
          key={item.id}
          isSelected={pathDirect === item?.href}
          borderRadius='8px'
          icon={itemIcon}
          link={item.href}
          component={Link}
        >
          {item.title}
        </MenuItem >
      </Box>

    );
  });
};


const SidebarItems = () => {
  const pathname = usePathname();
  const pathDirect = pathname;

  return (
    <MUI_Sidebar width={"100%"} showProfile={false} themeColor={"#1652F0"} themeSecondaryColor={'#19C6FF'}>
      <Box sx={{ px: 3, pt: 2.5, pb: 1.5 }}>
        <AppLogo />
      </Box>

      {renderMenuItems(Menuitems, pathDirect)}
    </MUI_Sidebar>
  );
};
export default SidebarItems;
