import { themeQuartz } from 'ag-grid-community';

// to use myTheme in an application, pass it to the theme grid option
export const myTheme = themeQuartz
    .withParams({
        accentColor: "#00A2FF",
        backgroundColor: "#21222C",
        borderColor: "#429356",
        borderRadius: 0,
        browserColorScheme: "dark",
        cellHorizontalPaddingScale: 0.8,
        cellTextColor: "#50F178",
        columnBorder: true,
        fontFamily: {
            googleFont: "IBM Plex Mono"
        },
        fontSize: 12,
        foregroundColor: "#68FF8E",
        headerBackgroundColor: "#21222C",
        headerFontWeight: 700,
        headerTextColor: "#68FF8E",
        headerVerticalPaddingScale: 1.5,
        oddRowBackgroundColor: "#21222C",
        rangeSelectionBackgroundColor: "#FFFF0020",
        rangeSelectionBorderColor: "yellow",
        rangeSelectionBorderStyle: "dashed",
        rowBorder: true,
        rowVerticalPaddingScale: 1.5,
        sidePanelBorder: true,
        spacing: 4,
        wrapperBorder: true,
        wrapperBorderRadius: 0
    });
