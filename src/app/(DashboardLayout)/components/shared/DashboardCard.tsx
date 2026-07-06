import React from "react";
import { Card, CardContent, Typography, Stack, Box } from "@mui/material";

type Props = {
  title?: string;
  subtitle?: string;
  action?: React.ReactNode | any;
  footer?: React.ReactNode;
  cardheading?: string | React.ReactNode;
  headtitle?: string | React.ReactNode;
  headsubtitle?: string | React.ReactNode;
  children?: React.ReactNode;
  middlecontent?: string | React.ReactNode;
  contentSx?: object;
  sx?: object;
  fillHeight?: boolean;
};

const DashboardCard = ({
  title,
  subtitle,
  children,
  action,
  footer,
  cardheading,
  headtitle,
  headsubtitle,
  middlecontent,
  contentSx,
  sx,
  fillHeight,
}: Props) => {
  return (
    <Card
      sx={{
        padding: 0,
        width: "100%",
        minWidth: 0,
        ...(fillHeight
          ? { height: "100%", display: "flex", flexDirection: "column" }
          : {}),
        ...sx,
      }}
      elevation={9}
      variant={undefined}
    >
      {cardheading ? (
        <CardContent>
          <Typography variant="h5">{headtitle}</Typography>
          <Typography variant="subtitle2" color="textSecondary">
            {headsubtitle}
          </Typography>
        </CardContent>
      ) : (
        <CardContent
          sx={{
            p: { xs: "20px", sm: "30px" },
            minWidth: 0,
            ...(fillHeight ? { flex: 1, display: "flex", flexDirection: "column" } : {}),
            ...contentSx,
          }}
        >
          {title ? (
            <Stack
              direction="row"
              spacing={2}
              justifyContent="space-between"
              alignItems={"center"}
              mb={3}
            >
              <Box>
                {title ? <Typography variant="h5">{title}</Typography> : ""}

                {subtitle ? (
                  <Typography variant="subtitle2" color="textSecondary">
                    {subtitle}
                  </Typography>
                ) : (
                  ""
                )}
              </Box>
              {action}
            </Stack>
          ) : null}

          <Box sx={fillHeight ? { flex: 1, display: "flex", flexDirection: "column", minHeight: 0 } : undefined}>
            {children}
          </Box>
        </CardContent>
      )}

      {middlecontent}
      {footer}
    </Card>
  );
};

export default DashboardCard;
